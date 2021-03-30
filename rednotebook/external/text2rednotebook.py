"""
Mass import diary/journal entries from markdown/plain text/odt into rednotebook
"""

import argparse
import sys
import re
import datetime
from odf import text
from odf.opendocument import load
sys.path.append('/usr/share/rednotebook')

# must import rednotebook after munging path in order to find it, as it is
# not (at least in Debian) installed in the default python path
import rednotebook.storage  # pylint: disable=wrong-import-position, unused-import

def main():
    """ parse commandline arguments & process text """

    parser = argparse.ArgumentParser()
    parser.add_argument('-n', '--dry-run', action='store_true')
    parser.add_argument('--echo-entries', action='store_true')
    parser.add_argument('--existing', choices=['overwrite', 'append', 'skip', 'error'],
                        default='error')
    parser.add_argument('--no-list-missing-entries', action='store_true')
    parser.add_argument('infile')
    args = parser.parse_args()
    if args.infile.endswith('.odt'):
        textdoc = load(args.infile)
        alltext = [str(para) for para in textdoc.getElementsByType(text.P)]
        alltext = "\n\n".join(alltext)
    else:
        with open(args.infile) as fin:
            alltext = fin.read()

    # remove non-printable characters
    control_chars = ''.join(map(chr, range(0x7f,0xa0)))
    control_char_re = re.compile('[%s]' % re.escape(control_chars))
    alltext = control_char_re.sub('', alltext)

    days = re.split(r'(\w+day[,]?\s*\d+\s+\w+\s+\d+)\.?\s*', alltext, flags=re.IGNORECASE)
    i = 0
    if days:
        print(f'Found entries for {(len(days)-1)//2} days')
        if days[0] != '':
            print(f"Ignoring leading text: {days[0]}")
        i += 1

    # have to import *after* munging argv as rednotebook does its own argv parsing
    sys.argv = [sys.argv[0]]
    import rednotebook.journal  # pylint: disable=import-outside-toplevel, redefined-outer-name
    journal = rednotebook.journal.Journal()
    data_dir = journal.get_journal_path()
    existing_entries = rednotebook.storage.load_all_months_from_disk(data_dir)
    months = {}
    mindate, maxdate = None, None
    while i < len(days):
        if args.echo_entries:
            print(f"Date: {days[i]}")
        try:
            dateobj = datetime.datetime.strptime(days[i], '%A, %d %B %Y')
        except ValueError as err:
            raise ValueError(f"'{days[i]}' is not a valid date") from err

        # strptime seems to be rather lax about parsing day/date combinations,
        # so check manually
        weekday = re.search(r'(\w+day)', days[i])
        weekday = weekday.group(0)
        if dateobj.strftime('%A') != weekday:
            raise ValueError(
                f"'{days[i]}' is not a valid date. {dateobj.strftime('%d %B %Y')} " +
                f"was a {dateobj.strftime('%A')}.")

        if mindate is None or dateobj < mindate:
            mindate = dateobj
        if maxdate is None or dateobj > maxdate:
            maxdate = dateobj

        monthstr = dateobj.strftime('%Y-%m')
        daynum = int(dateobj.strftime('%d'))
        month = None
        if monthstr in months:
            month = months[monthstr]
        elif monthstr in existing_entries:
            month = existing_entries[monthstr]
        else:
            month = rednotebook.data.Month(int(dateobj.strftime('%Y')), int(dateobj.strftime('%m')))
        day = month.get_day(daynum)

        if not day.empty:
            if args.existing == 'skip':
                print(f"Entry for {days[i]} already exists. Skipping.")
            elif args.existing == 'error':
                print(f"Error: entry for {days[i]} already exists.")
                sys.exit(1)
            i += 2
            continue

         # remove blank headers
        days[i+1] = re.sub(r"^\s*[#]+\s*$", "", days[i+1], flags=re.MULTILINE)

        # remove leading blank lines
        days[i+1] = re.sub(r"^\s*\n", "", days[i+1])

        # remove trailing blank lines
        days[i+1] = re.sub(r"\n$", "", days[i+1])
        if args.echo_entries:
            print(days[i+1])
        if not day.empty and args.existing == 'append':
            day.content[text] += f"\n\n{days[i+1]}"
        else:
            day.content = {'text': days[i+1]}
        months[monthstr] = month
        i += 2

    if not args.no_list_missing_entries:
        list_missing_entries(mindate, maxdate, months, existing_entries)

    if not args.dry_run:
        rednotebook.storage.save_months_to_disk(months, data_dir, True, True)


if __name__ == "__main__":
    main()


def list_missing_entries(mindate, maxdate, months, existing_entries):
    """ list missing entries """

    for i_day in range(int((maxdate - mindate).days)):
        dateobj = mindate + datetime.timedelta(i_day)
        monthstr = dateobj.strftime('%Y-%m')
        daynum = int(dateobj.strftime('%d'))
        month = None
        day = None
        if monthstr in months:
            month = months[monthstr]
        elif monthstr in existing_entries:
            month = existing_entries[monthstr]
        else:
            print(f"Missing entries for {dateobj.strftime('%B %Y')}")
            continue
        day = month.get_day(daynum)
        if day.empty:
            print(f"Missing entry for {dateobj.strftime('%d %B %Y')}")
