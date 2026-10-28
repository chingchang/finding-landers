HiRISE strips for the lander search (prepared 2026-10-26)
manifest.txt     case  observation_id  url_base   (66 strips: 16 control, 34 Polar Lander summer, 7 Polar Lander other seasons, 9 Mars 3)
download_hirise.sh [case-regex]   resumable downloader, 3 at a time, log in download.log, strips land in strips/<case>/
Suggested order (disk is tight at 66 GB free):
  ./download_hirise.sh 'control'              about 6 GB
  ./download_hirise.sh 'mpl_summer'           about 39 GB
  ./download_hirise.sh 'mars3|mpl_other'      later, after tiling, or onto an external drive
Credit: NASA/JPL/University of Arizona. Source: PDS RDR V1.1 at hirise.lpl.arizona.edu/PDS/RDR/
