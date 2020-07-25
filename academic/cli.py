#!/usr/bin/env python3

import subprocess
import sys
import os
import re
import argparse
from argparse import RawTextHelpFormatter
from pathlib import Path
import calendar
import logging
from datetime import datetime
from academic import __version__ as version
from academic.import_assets import import_assets

import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.bwriter import BibTexWriter
from bibtexparser.bibdatabase import BibDatabase
from bibtexparser.customization import convert_to_unicode


# Map BibTeX to Academic publication types.
PUB_TYPES = {
    "article": 2,
    "book": 5,
    "inbook": 6,
    "incollection": 6,
    "inproceedings": 1,
    "manual": 4,
    "mastersthesis": 7,
    "misc": 0,
    "phdthesis": 7,
    "proceedings": 0,
    "techreport": 4,
    "unpublished": 3,
    "patent": 8,
}

# Initialise logger.
logging.basicConfig(format="%(asctime)s %(levelname)s: %(message)s", level=logging.WARNING, datefmt="%I:%M:%S%p")
log = logging.getLogger(__name__)


class AcademicError(Exception):
    pass


def main():
    parse_args(sys.argv[1:])  # Strip command name, leave just args.


def parse_args(args):
    """Parse command-line arguments"""

    # Initialise command parser.
    parser = argparse.ArgumentParser(
        description=f"Academic Admin Tool v{version}\nhttps://sourcethemes.com/academic/", formatter_class=RawTextHelpFormatter
    )
    subparsers = parser.add_subparsers(help="Sub-commands", dest="command")

    # Sub-parser for import command.
    parser_a = subparsers.add_parser("import", help="Import data into Academic")
    parser_a.add_argument("--assets", action="store_true", help="Import third-party JS and CSS for generating an offline site")
    parser_a.add_argument("--bibtex", required=False, type=str, help="File path to your BibTeX file")
    parser_a.add_argument(
        "--publication-dir",
        required=False,
        type=str,
        default="publication",
        help="Directory that your publications are stored in (default `publication`)",
    )
    parser_a.add_argument("--featured", action="store_true", help="Flag publications as featured")
    parser_a.add_argument("--overwrite", action="store_true", help="Overwrite existing publications")
    parser_a.add_argument("--normalize", action="store_true", help="Normalize each keyword to lowercase with uppercase first letter")
    parser_a.add_argument("-v", "--verbose", action="store_true", required=False, help="Verbose mode")
    parser_a.add_argument("-dr", "--dry-run", action="store_true", required=False, help="Perform a dry run (Bibtex only)")

    known_args, unknown = parser.parse_known_args(args)

    # If no arguments, show help.
    if len(args) == 0:
        parser.print_help()
        parser.exit()

    # If no known arguments, wrap Hugo command.
    elif known_args is None and unknown:
        cmd = []
        cmd.append("hugo")
        if args:
            cmd.append(args)
        subprocess.call(cmd)
    else:
        # The command has been recognised, proceed to parse it.
        if known_args.command and known_args.verbose:
            # Set logging level to debug if verbose mode activated.
            logging.getLogger().setLevel(logging.DEBUG)
        if known_args.command and known_args.assets:
            # Run command to import assets.
            import_assets()
        elif known_args.command and known_args.bibtex:
            # Run command to import bibtex.
            import_bibtex(
                known_args.bibtex,
                pub_dir=known_args.publication_dir,
                featured=known_args.featured,
                overwrite=known_args.overwrite,
                normalize=known_args.normalize,
                dry_run=known_args.dry_run,
            )


def import_bibtex(bibtex, pub_dir="publication", featured=False, overwrite=False, normalize=False, dry_run=False):
    """Import publications from BibTeX file"""

    # Check BibTeX file exists.
    if not Path(bibtex).is_file():
        err = "Please check the path to your BibTeX file and re-run"
        log.error(err)
        raise AcademicError(err)

    log.info(f'Opening file for members and alumni information')
    member_path = "content/member"
    member_file = os.path.join(member_path, "member.txt")
    member_first = []
    member_last = []
    member_link = []
    if Path(member_file).is_file() :
        with open(member_file, 'r') as file_in:
            for line in file_in:
                words = line.rstrip("\n").split()
                member_link.append(words[0])
                member_last.append(words[1])
                member_first.append(words[2])
    else:
        err = f"Please check that the member.txt file exists in {member_path}"
        log.error(err)
        raise AcademicError(err)

    alumni_path = "content/alumni"
    alumni_file = os.path.join(alumni_path, "alumni.txt")
    alumni_first = []
    alumni_last = []
    alumni_link = []
    if Path(alumni_file).is_file() :
        with open(alumni_file, 'r') as file_in:
            for line in file_in:
                words = line.rstrip("\n").split()
                alumni_link.append(words[0])
                alumni_last.append(words[1])
                alumni_first.append(words[2])
    else:
        err = f"Please check that the alumni.txt file exists in {alumni_path}"
        log.error(err)
        raise AcademicError(err)

    # Load BibTeX file for parsing.
    with open(bibtex, "r", encoding="utf-8") as bibtex_file:
        parser = BibTexParser(common_strings=True)
        parser.customization = convert_to_unicode
        parser.ignore_nonstandard_types = False
        bib_database = bibtexparser.load(bibtex_file, parser=parser)
        for entry in bib_database.entries:
            parse_bibtex_entry(entry, member_first, member_last, member_link, alumni_first, alumni_last, alumni_link, pub_dir=pub_dir, featured=featured, overwrite=overwrite, normalize=normalize, dry_run=dry_run)


def parse_bibtex_entry(entry, member_first, member_last, member_link, alumni_first, alumni_last, alumni_link, pub_dir="publication", featured=False, overwrite=False, normalize=False, dry_run=False):
    """Parse a bibtex entry and generate corresponding publication bundle"""
    log.info(f"Parsing entry {entry['ID']}")

    bundle_path = f"content/{pub_dir}"
    bundle_path2 = f"static/bib/{pub_dir}"
    markdown_path = os.path.join(bundle_path, f"{slugify(entry['ID'])}.md")
    cite_path = os.path.join(bundle_path2, f"{slugify(entry['ID'])}.bib")
    date = datetime.utcnow()
    timestamp = date.isoformat("T") + "Z"  # RFC 3339 timestamp.

    # Do not overwrite publication bundle if it already exists.
    if not overwrite and os.path.isdir(bundle_path):
        log.warning(f"Skipping creation of {bundle_path} as it already exists. " f"To overwrite, add the `--overwrite` argument.")
        return

    # Create bundle dir.
    log.info(f"Creating folder {bundle_path}")
    if not dry_run:
        Path(bundle_path).mkdir(parents=True, exist_ok=True)

    # Save citation file.
    log.info(f"Saving citation to {cite_path}")
    db = BibDatabase()
    db.entries = [entry]
    writer = BibTexWriter()
    if not dry_run:
        with open(cite_path, "w", encoding="utf-8") as f:
            f.write(writer.write(db))

    # Prepare YAML front matter for Markdown file.
    frontmatter = ["+++"]
    frontmatter.append(f'title = "{clean_bibtex_str(entry["title"])}"')
    year = ""
    month = "01"
    day = "01"
    if "date" in entry:
        dateparts = entry["date"].split("-")
        if len(dateparts) == 3:
            year, month, day = dateparts[0], dateparts[1], dateparts[2]
        elif len(dateparts) == 2:
            year, month = dateparts[0], dateparts[1]
        elif len(dateparts) == 1:
            year = dateparts[0]
    if "month" in entry and month == "01":
        month = month2number(entry["month"])
    if "year" in entry and year == "":
        year = entry["year"]
    if len(year) == 0:
        log.error(f'Invalid date for entry `{entry["ID"]}`.')
    frontmatter.append(f"date =  {year}-{month}-{day}")

    frontmatter.append(f"publishDate = {timestamp}")


    frontmatter.append(f'publication_types =  ["{PUB_TYPES.get(entry["ENTRYTYPE"], 0)}"]')

    abstract_file = os.path.join(bundle_path2, f"{slugify(entry['ID'])}.abs")
    if "abstract" in entry:
        frontmatter.append(f'abstract =  "{clean_bibtex_str(entry["abstract"])}"')
    elif os.path.exists(abstract_file):
        log.info(f"Reading abstract from '{abstract_file}'")
        _abstract = ''.join(open(abstract_file, 'r').readlines()).rstrip("\n")
        log.info(f"{clean_abstract_str(_abstract)}")
        frontmatter.append(f'abstract = "{clean_abstract_str(_abstract)}"')
    else:
        frontmatter.append('abstract =  ""')

    frontmatter.append(f"selected = {str(featured).lower()}")

    vol = ""
    if "volume" in entry:
        vol = entry["volume"]
    pages = ""
    if "pages" in entry:
        pages = entry["pages"]

    # Publication name.
    if "booktitle" in entry:
        frontmatter.append(f'publication = "*{clean_bibtex_str(entry["booktitle"])}*"')
    elif "journal" in entry:
        if len(vol) == 0:
             frontmatter.append(f'publication = "{clean_bibtex_str(entry["journal"])} {pages} ({year})."')
        else:
             frontmatter.append(f'publication = "{clean_bibtex_str(entry["journal"])} **{vol}**, {pages} ({year})."')
    elif "publisher" in entry:
        frontmatter.append(f'publication = "*{clean_bibtex_str(entry["publisher"])}*"')
    else:
        frontmatter.append('publication =  ""')

    if "keywords" in entry:
        frontmatter.append(f'tags: [{clean_bibtex_tags(entry["keywords"], normalize)}]')

    if "url" in entry:
        frontmatter.append(f'url_url =  "{clean_bibtex_str(entry["url"])}"')

    if "doi" in entry:
        frontmatter.append(f'url_doi =  "https://doi.org/{entry["doi"]}"')

    if "pdf" in entry:
        frontmatter.append(f'url_pdf =  "pdf/publication/{entry["pdf"]}"')

    # Add a link to the bib file 
    frontmatter.append(f'url_bib =  "bib/publication/{slugify(entry["ID"])}.bib"')


    authors = None
    if "author" in entry:
        authors = entry["author"]
    elif "editor" in entry:
        authors = entry["editor"]
    if authors:
        authors, member, alumni = clean_bibtex_authors([i.strip() for i in authors.replace("\n", " ").split(" and ")], member_first, member_last, member_link, alumni_first, alumni_last, alumni_link)
        frontmatter.append(f"")
        for i, a in enumerate(authors):
             frontmatter.append(f"[[authors]]")
             frontmatter.append(f"    name = {a}")
             if member[i] == "" and alumni[i] == "":
                 frontmatter.append(f"    is_member = false")
                 frontmatter.append(f"    link = \"\"\n")
             elif alumni[i] == "":
                 frontmatter.append(f"    is_member = true")
                 frontmatter.append(f"    link = \"/{member[i]}\"\n")
             else:
                 frontmatter.append(f"    is_former_member = true")
                 frontmatter.append(f"    link = \"/alumni/{alumni[i]}\"\n")

    frontmatter.append("+++\n\n")

    # Save Markdown file.
    try:
        log.info(f"Saving Markdown to '{markdown_path}'")
        if not dry_run:
            with open(markdown_path, "w", encoding="utf-8") as f:
                f.write("\n".join(frontmatter))
    except IOError:
        log.error("Could not save file.")


def slugify(s, lower=True):
    bad_symbols = (".", "_", ":")  # Symbols to replace with hyphen delimiter.
    delimiter = "-"
    good_symbols = (delimiter,)  # Symbols to keep.
    for r in bad_symbols:
        s = s.replace(r, delimiter)

    s = re.sub(r"(\D+)(\d+)", r"\1\-\2", s)  # Delimit non-number, number.
    s = re.sub(r"(\d+)(\D+)", r"\1\-\2", s)  # Delimit number, non-number.
    s = re.sub(r"((?<=[a-z])[A-Z]|(?<!\A)[A-Z](?=[a-z]))", r"\-\1", s)  # Delimit camelcase.
    s = "".join(c for c in s if c.isalnum() or c in good_symbols).strip()  # Strip non-alphanumeric and non-hyphen.
    s = re.sub("-{2,}", "-", s)  # Remove consecutive hyphens.

    if lower:
        s = s.lower()
    return s


def clean_bibtex_authors(author_str,member_first, member_last, member_link, alumni_first, alumni_last, alumni_link):
    """Convert author names to `firstname(s) lastname` format."""
    authors = []
    member = []
    alumni = []
    for s in author_str:
        s = s.strip()
        if len(s) < 1:
            continue
        if "," in s:
            split_names = s.split(",", 1)
            last_name = split_names[0].strip()
            first_names = [i.strip() for i in split_names[1].split()]
        else:
            split_names = s.split()
            last_name = split_names.pop()
            first_names = [i.replace(".", ". ").strip() for i in split_names]
        if last_name in ["jnr", "jr", "junior"]:
            last_name = first_names.pop()
        for item in first_names:
            if item in ["ben", "van", "der", "de", "la", "le"]:
                last_name = first_names.pop() + " " + last_name
        authors.append(f'"{" ".join(first_names)} {last_name}"')
 
        # Member matching
        matched = -1
        lastnamematch = [i for i, j in enumerate(member_last) if j == last_name]
        for i in lastnamematch:
            if first_names[0] == member_first[i]:
                matched = i
                break
            elif first_names[0][0] == member_first[i][0]:
                matched = i
                break

        if matched >= 0:
            member.append(member_link[matched])
        else:
            member.append("")

        #Alumni matching
        matched = -1
        lastnamematch = [i for i, j in enumerate(alumni_last) if j == last_name]
        for i in lastnamematch:
            if first_names[0] == alumni_first[i]:
                matched = i
                break
            elif first_names[0][0] == alumni_first[i][0]:
                matched = i
                break
        if matched >= 0:
            alumni.append(alumni_link[matched])
        else:
            alumni.append("")

    return authors, member, alumni


def clean_bibtex_str(s):
    """Clean BibTeX string and escape TOML special characters"""
    s = s.replace("\\", "")
    s = s.replace('"', '\\"')
    s = s.replace("{", "").replace("}", "")
    s = s.replace("\t", " ").replace("\n", " ").replace("\r", "")
    #Ugly hack
    s = s.replace("1-x","{1-x}")
    return s

def clean_abstract_str(s):
    """Clean BibTeX string and escape TOML special characters"""
    s = s.replace("{\\em ab initio}", "*ab initio*")
    s = s.replace("{\\em Ab initio}", "*Ab initio*")
    s = s.replace("{\\em all}", "*all*")
    s = s.replace("{\\em effective}", "*effective*")
    s = s.replace("\\texttt{BerkeleyGW}", "<TT>BerkeleyGW</TT>")
    s = s.replace("\\texttt{PARATEC}", "<TT>PARATEC</TT>")
    s = s.replace("\\texttt{PARSEC}", "<TT>PARSEC</TT>")
    s = s.replace("\\texttt{Quantum ESPRESSO}", "<TT>Quantum ESPRESSO</TT>")
    s = s.replace("\\texttt{SIESTA}", "<TT>SIESTA</TT>")
    s = s.replace("\\texttt{Octopus}", "<TT>Octopus</TT>")
    s = s.replace("$\\lesssim$", "&le;")
    s = s.replace("$\\propto$", "&prop;")
    s = s.replace("$\\times$", "&times;")
    s = s.replace("$\\sim$", "&sim;")
    s = s.replace("$\\rightarrow$", "&rarr;")
    s = s.replace("$\\tau_", "&tau;$_")
    s = s.replace("$\\pi$", "&pi;")
    s = s.replace("$\\mu$", "&micro;")
    s = s.replace("$\\rho$", "&rho;")
    s = s.replace("$\\theta$", "&theta;")
    s = s.replace("$\\alpha$", "&alpha;")
    s = s.replace("$\\beta$", "&beta;")
    s = s.replace("$\\Gamma$", "&Gamma;")
    s = s.replace("$\\gamma$", "&gamma;")
    s = s.replace("$\\Sigma$", "&Sigma;")
    s = s.replace("$\\Sigma(\\omega)$", "&Sigma;(&omega;)")
    s = s.replace("$^{\\circ}$", "&deg;")
    s = s.replace("\\", "")
    s = s.replace('"', '\\"')
    s = s.replace("{", "").replace("}", "")
    s = s.replace("\t", " ").replace("\n", " ").replace("\r", "")
    #Ugly hack
    s = s.replace("1-x","{1-x}")
    s = s.replace("12-x","{12-x}")
    s = s.replace("13-x","{13-x}")
    s = s.replace("$_13$","$_{13}$")
    s = s.replace("$_0.5$","$_{0.5}$")
    s = s.replace("$_11.5$","$_{11.5}$")
    s = s.replace("$_11$","$_{11}$")
    s = s.replace("$_12.75$","$_{12.75}$")
    s = s.replace("$_0.25$","$_{0.25}$")
    s = s.replace("D$_Zn$","D$_{Zn}$")
    s = s.replace("D$_Te$","D$_{Te}$")
    s = s.replace("D$_Si$","D$_{Si}$")
    s = s.replace("D$_Ge$","D$_{Ge}$")
    s = s.replace("$^-1$","$^{-1}$")
    s = s.replace("$^-2$","$^{-2}$")
    s = s.replace("$^-4$","$^{-4}$")
    s = s.replace("$^-5$","$^{-5}$")
    s = s.replace("$^1+$","$^{1+}$")
    s = s.replace("$^2+$","$^{2+}$")
    s = s.replace("$^+2$","$^{+2}$")
    s = s.replace("$^3+$","$^{3+}$")
    s = s.replace("$^+3$","$^{+3}$")
    s = s.replace("0$_60$","0$_{60}$")
    s = s.replace("$_1g$","$_{1g}$")
    s = s.replace("$_2g","$_{2g}")
    s = s.replace("_2g$","_{2g}$")
    return s

def clean_bibtex_tags(s, normalize=False):
    """Clean BibTeX keywords and convert to TOML tags"""
    tags = clean_bibtex_str(s).split(",")
    tags = [f'"{tag.strip()}"' for tag in tags]
    if normalize:
        tags = [tag.lower().capitalize() for tag in tags]
    tags_str = ", ".join(tags)
    return tags_str


def month2number(month):
    """Convert BibTeX or BibLateX month to numeric"""
    if len(month) <= 2:  # Assume a 1 or 2 digit numeric month has been given.
        return month.zfill(2)
    else:  # Assume a textual month has been given.
        month_abbr = month.strip()[:3].title()
        try:
            return str(list(calendar.month_abbr).index(month_abbr)).zfill(2)
        except ValueError:
            raise log.error("Please update the entry with a valid month.")


if __name__ == "__main__":
    main()
