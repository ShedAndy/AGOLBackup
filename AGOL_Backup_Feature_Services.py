#-------------------------------------------------------------------
# Script to backup hosted feature services that have a specific tag.  
#
# **WARNING** If run more than once on the same day, the previously 
# downloaded files will be overwritten (unless you re-named or 
# moved them before re-running the script)
#
# Older versions of the API may fail when trying to download zipfile
# containing the fgdb as support for FileName = "" in item.download()
# is seemly a recent development at time of writing.
#
# Andy Fairbairn, 2020. 
#-------------------------------------------------------------------

#-------------------------------------------------------------------
# PARAMETERS
#-------------------------------------------------------------------
# Portal Credentials
portal_url = "https://www.arcgis.com"
username = ""
password = ""

# Full Backup - if true, attempts to backup all tagged hosted feature services (HFS)
# if false, only backs up those that have been edited since the last successful
# backup of that HFS
full_backup = False

# Tag - tag used to indicate that the hosted feature service needs backing up 
# (don't use this tag for anything else!)
tag = 'backmeup'

# Download location - the zipped file geodatabases will be put into a folder named by date. 
# Make sure this location is writable. No trailing slash on end of folder path!!
#download_location = r"C:\TestBackupFolder"
download_location = r"\\BBOWTBIODATA\ArcGIS Online Scripts\Backup"

# File name for the record of successful backups - saved in download location
successful_backups = 'Last_Successful_Backup.csv'

# Time to pause (minutes) - time between starting exporting to FGDBs and downloading the zip files.
# Download seems to be available before exporting is complete, leading to invalid zip files being
# downloaded.  Add a pause time to wait before attempting to download - time required will
# depend on how large your feature service (inc. attachments) is.
sleep_time = 60

# If invalid zip files are downloaded, time to wait before re-attempting to download
reattempt_time = 60

# Number of reattempts if downloaded files are invalid
no_attempts = 3

# Max number of services to back up - searching has maximum number of results to return.
# Set this to be higher than the number of hosted feature services with the 
# backup tag that you want to backup
max_results = 50
#-------------------------------------------------------------------

#--------------------------------------------------------------------
# PRINT MESSAGE TO USERS WHO MIGHT BE CONFUSED BY SCHEDULED TASK!
#---------------------------------------------------------------------
print("\n\n*****ArcGIS Online BACKUP SCRIPT*****")
print("*****DO NOT CLOSE THIS WINDOW WHILST RUNNING!!!*****\n")
print("You can minimise this window and work as normal.")
print("When the script has completed it will say BACKUP COMPLETED, at which")
print("point you can close this window if it doesn't do so automatically.\n")

#-------------------------------------------------------------------
# MODULES
#-------------------------------------------------------------------
from arcgis.gis import GIS
from IPython.display import display
from datetime import datetime, date
import time
import os
import zipfile
import pandas as pd
#-------------------------------------------------------------------

# log into portal
gis = GIS(portal_url, username, password)

# Today's date, used in file path of downloaded backups
date_today_obj = date.today()
date_today = date_today_obj.strftime('%Y%m%d')
year = date_today_obj.strftime('%Y')
month = date_today_obj.strftime('%m')
ts_today = int(round(datetime.now().timestamp()*1000,0))

# Log for this backup run
run_log_folder = download_location + '\\logs'

# Where the log last successfull backup log will be kept
success_log_csv_path = download_location + '\\' + successful_backups
#success_log_csv_path = r"D:\ArcGIS Online Backups\test\Last_Successful_Backup.csv"

#-------------------------------------------------------------------
# GENERAL FUNCTIONS
#-------------------------------------------------------------------

def stamp_to_text(ts):
    return datetime.utcfromtimestamp(ts/1e3).strftime('%d/%m/%Y %H:%M:%S')

def check_create_folder(path):
    if not os.path.isdir(path):
        print(path + " doesn't exist - attempting to create it")
        try:
            os.makedirs(path)
        except:
            print("Unable to create folder, check permissions")

def set_indexes(df_list,index):
    for df in df_list:
        if df.index.name != index:
            df.set_index(index, inplace=True)

def reset_indexes(df_list):
    for df in df_list:
        if df.index.name is not None:
            df.reset_index(inplace=True)

def update_df(df,updating_df):
    # Set the dataframe indexes to a matching field
    set_indexes([df,updating_df],'item_id')
    
    # Update exising rows in the df with values from updating_df
    df.update(updating_df)
    
    # Append rows from updating_df that are not in df
    index_diff = updating_df.index.difference(df.index)
    updated_df = df.append(updating_df.loc[index_diff.values.tolist(),:], sort=False)
    
    # Reset dataframe indexes to the default
    reset_indexes([df,updating_df,updated_df])
    return updated_df

def export_df(df,path):
    try:
        # Write updated values out to last successful backup csv
        df.to_csv(path, index = False)
        return True
    except:
        print("Unable to write dataframe to {} - Open in Excel? Check permissions for the folder.".format(path))
        return False

#-------------------------------------------------------------------
# SEARCH FOR HOSTED FEATURE SERVICES TO BACKUP
#-------------------------------------------------------------------

# Search based on the specified tag, limit type to Feature Layer
# Returns a maximum of 50 results, so increase this if you have more than 50
# feature services to backup using max_results parameter
item_list = gis.content.search(query="tags:"+tag, item_type = "Feature Layer", max_items = max_results)
print('Found {} feature service(s) with the tag "{}" to backup\n'.format(len(item_list),tag))

if len(item_list) < 1:
    exit()

#-------------------------------------------------------------------
# UPDATE INFO ON HOSTED FEATURE SERVICES
#-------------------------------------------------------------------

def item_info(item):
    # Function to take an item id and return last update date of the
    # of the item, and the last edit date of feature class or tables
    
    updated_ts = item.modified
    
    # Get the last_edit_date for the HFS item - believe the only way
    # to get this is to check each layer and table in feature service
    # last edit date across all item layers and tables
    last_edit_date_ts = 0 
    
    if item._has_layers() == True:
        for flyr in item.layers:
            #print(flyr.properties.name)
            if flyr.properties.editingInfo.lastEditDate >= last_edit_date_ts:
                last_edit_date_ts = flyr.properties.editingInfo.lastEditDate

        for tbl in item.tables:
            #print(tbl.properties.name)
            if tbl.properties.editingInfo.lastEditDate >= last_edit_date_ts:
                last_edit_date_ts = tbl.properties.editingInfo.lastEditDate
    
    last_edit_date = stamp_to_text(last_edit_date_ts)
    
    return {'item_id':item.id,
            'item_name':item.name,
            'item_title':item.title,
            'updated_ts':updated_ts,
            'last_edit_date':last_edit_date,
            'last_edit_date_ts':last_edit_date_ts}

# Open or create log/list of last successful backups
success_log_exists = False

# Only backing up HFS that have been edited since last successful backup
# Try to open log used to check this, if unsuccessful just backup everthing
try:
    success_log_df = pd.read_csv(success_log_csv_path)
    success_log_exists = True
except:
    # Unsuccessful, so backup up all tagged HFS
    full_backup = True
    print("Couldn't open log of successful backups, backing up all services")
    print(success_log_csv_path)
    success_log_exists = False
    print("------------------")

# Gather info about items with the backup tag
item_info_list = []
for item in item_list:
    # item_info() returns a dictionary with layer/table last edit date and item update date
    item_info_list.append(item_info(item))

items_df = pd.DataFrame(item_info_list)
#success_log_df = pd.read_csv(success_log_csv_path)

if success_log_exists:
    # Update the last edited dates of items in the last good backup list
    # and add any not new items to be backed up that are not already in there
    success_log_df = update_df(success_log_df,items_df)

else:
    # Create a last good backup list from items_df
    success_log_df = items_df.copy()
    success_log_df.insert(5,"backup_date","Not yet backed up")
    success_log_df.insert(6,"backup_ts",0)
    success_log_df.insert(7,"zip_path","Not yet backed up")

# Export updated/newly created success_log_df
export_df(success_log_df, success_log_csv_path)

#if not a full backup, list of items that have a stale backup
if full_backup == False:
    query =  ((success_log_df['backup_ts'] < success_log_df['last_edit_date_ts'])
              | (success_log_df['backup_ts']!=success_log_df['backup_ts'])) 
    stale_list = success_log_df[query]['item_id'].values.tolist()
    #print(stale_list)

#-------------------------------------------------------------------
# EXPORT TO FGDB
#-------------------------------------------------------------------
# Export hosted feature service item to a fgdb item on AGOL
def export_to_fgdb(item):
    # Skip if we're not doing a full backup, and the id is not
    # on the list of items needing a fresh backup
    if (full_backup == True) or (item.id in stale_list):
        
        print("Exporting {} to fgdb".format(item.name))
        
        # create a name for the FGDB to be exported using today's date and the service name
        fgdb_name = date_today + '_' + item.name
        fgdb = item.export(fgdb_name, 'File Geodatabase', parameters=None, wait='True')
        download_list.append({'id':fgdb['exportItemId'], 'item_id':item.id, 'item_name':item.name})
        
        return fgdb
    
# download_list will be filled by calls to export_to_fgdb()
download_list = []

for item in item_list:
    fgdb = export_to_fgdb(item)

#-------------------------------------------------------------------
# DOWNLOAD ZIPPED FGDBs
#-------------------------------------------------------------------   

def download_fgdb(download):
    fgdb_item = gis.content.get(download['id'])
    
    #download_path = download_location + '\\' + year +'\\'+ month +'\\' + date_today
    download_path = download_location + '\\backups\\' + download['item_name']

    # If download_path folder doesn't exist, create it
    check_create_folder(download_path)

    try:
        # If using an older ArcGIS API version, file_name may not be a parameter of 
        # item.download, just have to go with save_path, and deal with fact any 
        # underscores in the fgdb name will be removed by default in a different way
        if fgdb_item.download(save_path=download_path, file_name=fgdb_item.name):
            print ('Downloading {} to {}'.format(fgdb_item.name,download_path ))                                
    except:
        print("Error - Unable to download {} to {}".format(fgdb_item.name,download_path ))

if len(download_list) > 0:
     # Pause to allow exporting to FGDB to complete
    print('Pausing for {} minutes to allow exporting to complete... \n'.format(sleep_time))

    # Convert sleep_time parameter, specified in minutes, into seconds
    #time.sleep(sleep_time*60)
    
    for download in download_list:
        download_fgdb(download)

#-------------------------------------------------------------------
# LOGS
#-------------------------------------------------------------------
# Check success of downloads and update log files accordingly
def zip_path(item):
    return r"{0}\backups\{1}\{2}_{1}.zip".format(download_location,item.name,date_today)

def check_zip(item):
        
    try:
        with zipfile.ZipFile(zip_path(item)) as test_result:
            #print('{} backup is OK'.format(item.name))
            test_result.close
            return 'success'
    except:
        print(item.name + " backup is invalid or doesn't exist")
        return 'fail'

def create_run_log():
    log_list = []
    for item in item_list:
        log_row = {'item_id':item.id,
                   'item_name':item.name,
                   'item_title':item.title,
                   'zip_path':zip_path(item),
                   'status': "Backup still fresh"}

        if (full_backup == True) or (item.id in stale_list): 
            log_row['status'] = check_zip(item)
        log_list.append(log_row)
    return log_list

def export_run_log():
    df = pd.DataFrame(create_run_log())
    check_create_folder(run_log_folder)
    run_log_path = r"{}\{}_backup_run_log.csv".format(run_log_folder,date_today)
    export_df(df,run_log_path)
    return df

def update_logs():
    # Export run log to csv and get a DataFrame
    run_df = export_run_log()
    # Use the run log to update last good backup list
    run_df.insert(len(run_df.columns),"backup_date",stamp_to_text(ts_today))
    run_df.insert(len(run_df.columns),"backup_ts",ts_today)
    update_df(success_log_df,run_df[run_df['status']=='success'])
    export_df(success_log_df,success_log_csv_path)
    return run_df

run_df = update_logs()

#-------------------------------------------------------------------
# RE-ATTEMPTS
#-------------------------------------------------------------------
# If there were any download failures, have another go after a pause
if len(download_list) > 0:
    fail_list = run_df[run_df['status']=='fail']['item_id'].values.tolist()
    attempts = 0
    if (len(fail_list) > 0) & (len(fail_list)!=len(download_list)):
        # At least one failure to download - or if all downloads, probably a more 
        # fundamental issue
        print('{} of {} fgdb zips did not download'.format(len(fail_list),len(download_list)))

        while attempts < no_attempts:

            if (len(fail_list) > 0):
                # PAUSE AGAIN
                # Time to wait before re-attempting to download fgdb

                print("Reattempting download in {} minutes".format(reattempt_time))

                time.sleep(reattempt_time*60)

                for download in download_list:
                    if download['item_id'] in fail_list:
                        download_fgdb(download)

                run_df = update_logs()

                fail_list = run_df[run_df['status']=='fail']['item_id'].values.tolist()

                attempts +=1
            else:
                attempts = 3

    success_list = run_df[run_df['status']=='success']['item_name'].values.tolist()
    print("\n{} of {} fgdb successfully downloaded".format(len(success_list),len(download_list)))
    for success in success_list:
        print(success)
    if (len(fail_list) > 0):
        print('\n{} of {} fgdb zips did not download'.format(len(fail_list),len(download_list)))
        fail_names = run_df[(run_df['status']=='fail')]['item_name'].values.tolist()
        for name in fail_names:
            print(name)
        #print("***try increasing the pause time between exporting and downloading the feature service****")

#-------------------------------------------------------------------
# DELETE FGDBs FROM PORTAL
#-------------------------------------------------------------------
# Now that the exported FGDBs have been downloaded as zips they can be
# deleted from the portal
def delete_fgdb(fgdb):
    # get the item object for the exported FGDB
    fgdb_item = gis.content.get(fgdb['id'])

    # delete the FGDB from AGOL
    print ('Deleting {} from {}'.format(fgdb['item_name'], portal_url))
    try:
        if fgdb_item.delete():
            print('Deleted!')
    except:
            print('ERROR - could  not delete {}'.format(fgdb['item_name']))

if len(download_list) > 0:
    for download in download_list:
        delete_fgdb(download)
        
print("BACKUP COMPLETED")
