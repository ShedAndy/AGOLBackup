# AGOL Backup Feature Services

## Backup tagged hosted feature services on ArcGIS Online to File Geodatabases.

A script to backup hosted feature services on ArcGIS Online that have previously been given a specific tag (e.g. "BackMeUp").  This script is designed to be run e.g. nightly as a scheduled task.  If a hosted feature service to be backed up has already been successfully backed up since it was last edited, then the script will not attempt to back it up again. Backups are downloaded to ./backups in the specified output (download) folder, and are filed by the services' name, and then by the date of the backup. A csv log of the each run of the script is saved in a ./logs folder, and a csv index of last successful backed ups, with their locations, is saved in the download folder.

As a minium before running, you need to set the following parameters at the start of the script:

*username* and *password* - for your portal

*tag* - the tag that you have used on AGOL to label the services you'd like to back up 

*download_location* - path where the outputs will be saved

**WARNING** If run more than once on the same day, the previously downloaded files will be overwritten IF there were edits in the interim, OR IF the previously downloaded zip was invalid, OR IF the full_backup parameter is set to True (unless of course you re-named or moved them before re-running the script!)

The script may fail if run on older versions of the API (OK on v1.6.1).  On older versions, failure may occur when trying to download the zipfile containing the fgdb, as support for FileName = "" in item.download() is seemly a recent development at time of writing.

A pause time (minutes) is speficed by the sleep_time parameter.  This is the time to wait between starting exporting feature services to FGDBs (saved on AGOL) and then downloading the FGDBs to a local location in zip files.  Downloading of the newly created FGDBs on AGOL seems to be available before exporting to FGDB is complete, which then leads to invalid zip files being downloaded.  The pause time allows the export to FGDB to complete before attempting to download - the time required will depend on the sizes of your feature services (inc. attachments).

Once one of my feature services went over 1.3GB, including attachments, I have found that exporting it to FGDB has become quite unreliable. Even with seemingly ample pause time specified, often an invalid zip may be downloaded. On a single run the script can re-attempt downloads a speficified number of times (no_attempts parameter) after a specified additional pause time (reattempt_time). If the download is still invalid at the end of the run, the script will attempt to back it up on the following run (even if there have been no further edits in the interim period). If anyone has any improvements to the way this script works that would avoid this issue, then I'd be very keen to hear about it (also often fails using the AGOL UI and these instructions for exporting large services to FGDB https://support.esri.com/en/technical-article/000012232)
