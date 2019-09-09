#!/usr/bin/env python
# coding: utf-8

# In[ ]:


#-------------------------------------------------------------------
# Script to backup hosted feature services that have a specific tag.  
#
# **WARNING** If run more than once on the same day, the previously 
# downloaded files will be overwritten (unless you re-named or 
# moved them before re-running the script)
#
# Older versions of the API may fail when trying to download tje zipfile
# containing the fgdb, as support for FileName = "" in item.download()
# is seemly a recent development at time of writing.
#
# Andy Fairbairn, 2019.
#-------------------------------------------------------------------

#--------------------------------------------------------------------
# PRINT MESSAGE TO USERS WHO MIGHT BE CONFUSED BY SCHEDULED TASK!
#---------------------------------------------------------------------
print("\n\n*****ArcGIS Online BACKUP SCRIPT*****")
print("*****DO NOT CLOSE THIS WINDOW WHILST RUNNING!!!*****\n")
print("You can minimise this window and work as normal.")
print("When the script as completed it will say BACKUP COMPLETED, at which")
print("point you can close this window if it doesn't do so automatically.\n")

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
tag = "backmeup"

# Download location - the zipped file geodatabases will be put into a folder named by date. 
# Make sure this location is writable. No trailing slash on end of folder path!!
#download_location = r"C:\TestBackupFolder"
download_location = r""

# File name for the record of successful backups - saved in download location
successful_backups = 'Last_Successful_Backup.csv'

# Time to pause (minutes) - time between starting exporting to FGDBs and downloading the zip files.
# Download seems to be available before exporting is complete, leading to invalid zip files being
# downloaded.  Therefore, add a pause time to wait before attempting to download - time required will
# depend on how large your feature service (inc. attachments) is.
sleep_time = 90

# Max number of services to back up - searching has maximum number of results to return parameter.
# Set this to be higher than the number of hosted feature services you want to backup
max_results = 50
#-------------------------------------------------------------------

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


# In[ ]:


# Today's date, used in file path of downloaded backups
date_today_obj = date.today()
date_today = date_today_obj.strftime('%Y%m%d')
year = date_today_obj.strftime('%Y')
month = date_today_obj.strftime('%m')

# Where the last successfull backup log will be kept
success_log_csv_path = download_location + '\\' + successful_backups

# Fields in the last successfull backup log that will be updated from current run log
update_fields = ["item_name", "item_title", "last_edit_date", "last_edit_date_ts", "path"]


# In[ ]:


#-------------------------------------------------------------------
# SEARCH FOR HOSTED FEATURE SERVICES TO BACKUP
#-------------------------------------------------------------------

# Search based on the specified tag, limit type to Feature Layer
# Returns a maximum of 50 results, so increase this if you have more than 50
# feature services to backup using max_results parameter
service_list = gis.content.search(query="tags:"+tag, item_type = "Feature Layer", max_items = max_results)
print('Found ' + str(len(service_list)) + ' feature service(s) with the tag "' + tag + '" to backup\n')

#-------------------------------------------------------------------
# PREVIOUS BACKUP INFO
#-------------------------------------------------------------------

# Initialize variable to determine if success log found and valid(ish)
# Used in BACKUP LOG - Part 2
success_log_exists = False

if full_backup == False:
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


# In[ ]:


#-------------------------------------------------------------------
# EXPORT TO FGDB
#-------------------------------------------------------------------

# list of dicts about HFS that have been backed up {item_id, item_name, item_title, item_led, item_led_ts, fgdb}
backup_list = []

# a list to contain log info for this backup run
log_list = []

# cycle through list of services with the tag
for service in service_list:
    # get the service as an item object
    item = gis.content.get(service.itemid)
    
    # double check that we're only dealing with hosted feature services, not views
    if ("Feature Service" in item.typeKeywords) and ("Hosted Service" in item.typeKeywords):
        
        # Get the last_edit_date for the HFS item - believe the only way
        # to get this is to check each layer and table in feature service
        # last edit date across all item layers and tables
        item_led_ts = 0 

        for flyr in item.layers:
            #print(flyr.properties.name)
            if flyr.properties.editingInfo.lastEditDate >= item_led_ts:
                item_led_ts = flyr.properties.editingInfo.lastEditDate

        for tbl in item.tables:
            #print(tbl.properties.name)
            if tbl.properties.editingInfo.lastEditDate >= item_led_ts:
                item_led_ts = tbl.properties.editingInfo.lastEditDate        
        
        item_led =datetime.utcfromtimestamp(item_led_ts/1e3).strftime('%d/%m/%Y %H:%M:%S')
        print('{0}: last edit date = {1}'.format(item.name, item_led))
        
        # If not doing a full backup, check if HFS edited since last backup
        if full_backup == False:
            
            if item.id in success_log_df['item_id'].values:
                # In successful back up log

                # Get the last_edit_date of the last successful backup
                led_ts_s = success_log_df.loc[success_log_df['item_id'] == item.id, 'last_edit_date_ts']
                success_log_led_ts = led_ts_s[led_ts_s.last_valid_index()]
                
                print("data last edit: {0} vs log last edit: {1} difference = {2}".format(item_led_ts, success_log_led_ts, (item_led_ts - success_log_led_ts)))
                
                # Continue For loop if HFS last_edit_data is not more recent
                # that what is in the successful backup log
                if not item_led_ts > success_log_led_ts:
                    # Not edited since last backup - record in log
                    
                    log_row = {"item_id":item.id, "item_name": item.name, "item_title":item.title, "last_edit_date": item_led, "last_edit_date_ts": item_led_ts, "path":"N/A", "status": "not backed up - no edits" }
                    log_list.append(log_row)
                    print("Not edited since last backup")
                    continue
        
        # create a name for the FGDB to be exported using today's date and the service name
        fgdb_name = date_today + '_' + item.name

        # export the current service to a FGDB, and add to a list
        print('Exporting ' + item.name + ' to a file geodatabase...')
        fgdb = service.export(fgdb_name, 'File Geodatabase', parameters=None, wait='True')

        # also add the feature service item to a list
        backup_list.append({'item_id':item.id, 'item_name':item.name, 'item_title':item.title, 'item_led':item_led, 'item_led_ts':item_led_ts, 'fgdb_name': fgdb_name, 'fgdb':fgdb})
    else:
        print('**** {0} ({1}) is not a hosted feature service, not exported ****'.format(item.title, item.name))
print(' ')       
print('Exporting {0} Feature Services to FGDB.'.format(len(backup_list)))


# In[ ]:


if len(backup_list) > 0:
    #-------------------------------------------------------------------
    # DOWNLOAD ZIPPED FGDBs
    #-------------------------------------------------------------------

    # Pause to allow exporting to FGDB to complete
    print('Pausing for ' + str(sleep_time) + ' minutes to allow exporting to complete... \n')

    # Convert sleep_time parameter, specified in minutes, into seconds
    time.sleep(sleep_time*60)
            
    # cycle through list of exported FGDBs, downloading them
    for backup in backup_list:
        # get the item object for the exported FGDB
        fgdb_item = gis.content.get(backup['fgdb']['exportItemId'])
        
        # make a path to save the downloaded to, in a sub-folder named today's date if it doesn't
        # already exist
        
        # Change here to file by e.g. date
        #download_path = download_location + '\\' + year +'\\'+ month +'\\' + date_today
        download_path = download_location + '\\backups\\' + backup['item_name']
        
        # Record the path of the downloaded zip for checking later
        backup['path'] = download_path + '\\' + backup['fgdb_name'] + ".zip"
        
        # If download_path folder doesn't exist, create it
        if not os.path.isdir(download_path):
            print(download_path + " doesn't exist - attempting to create it")
            try:
                os.makedirs(download_path)
            except:
                print("Unable to create folder, check permissions")
        
        # Download the file
        print ('Downloading ' + backup['fgdb_name'] + ' to ' + download_path +'...')
        
        try:
            # If using an older ArcGIS API version, file_name may not be a parameter of 
            # item.download, just have to go with save_path, and deal with fact any 
            # underscores in the fgdb name will be removed by default in a different way
            #if fgdb_item.download(save_path = download_path):
            if fgdb_item.download(save_path=download_path, file_name=(backup['fgdb_name']+".zip")):
                print('Downloaded!')                                
        except:
            print("Unable to download file")
                                  


# In[ ]:


#-------------------------------------------------------------------
# DELETE FGDBs FROM PORTAL
#-------------------------------------------------------------------
# Now that the exported FGDBs have been downloaded as zips they can be
# deleted from the portal
# Cycle through list of attempted backups, delete fgdb item
if len(backup_list) > 0:
    for backup in backup_list:
        # get the item object for the exported FGDB
        fgdb_item = gis.content.get(backup['fgdb']['exportItemId'])

        # delete the FGDB from AGOL
        print ('Deleting ' + fgdb_item.title + ' from ' + portal_url)
        if fgdb_item.delete():
            print('Deleted!')


# In[ ]:


#-----------------------------
# BACKUP LOG - Part 1
#-----------------------------
# Log for this run of the backup
# Test the validity of the downloaded zip file containing fgdb
# Result recorded in status field. This run log is is then used
# to update an overall record of the last successful backup of
# HFS in the backup schedule.
if len(backup_list)>0:
    for backup in backup_list:
        # Test whether downloaded fgdb exists and valid
        zip_path = backup['path']
        print("testing: " + zip_path)
        try:
            with zipfile.ZipFile(zip_path) as test_result:
                print(backup['item_title'] + ' backup is OK')
                test_result.close
                status = 'success'
        except:
            print(backup['item_title'] + " backup is invalid or doesn't exist")
            print("***try increasing the pause time between exporting and downloading the feature service****") 
            status = 'fail'
        log_row = {"item_id":backup['item_id'], "item_name": backup['item_name'], "item_title":backup['item_title'], "last_edit_date": backup['item_led'], "last_edit_date_ts": backup['item_led_ts'], "path":zip_path, "status": status }
        #print(log_row)
        log_list.append(log_row)

# Will log run even if no backups were made (len(backup_list)==0) because
# no HFS edited since last successful backup. If no HFS with the search
# tags were found in the first place, no run log will be created
if(len(log_list)>0):
    log_df = pd.DataFrame(log_list)

    # Save out csv file of run backup log
    
    # Check/Create log folder
    log_folder = download_location + '\\logs'
    if not os.path.isdir(log_folder):
        print(log_folder + "doesn't exist - attempting to create it")
        try:
            os.makedirs(log_folder)
        except:
            print("Unable to create log folder, check permissions")
    
    log_csv_path = log_folder + '\\' + date_today + '_backup_run_log.csv'
    try:
        log_df.to_csv(log_csv_path, index = False)
    except:
        print("Could not save log file - check permissions, does someone have it open in Excel?")
else:
    print("No feature services were found to backup")

    
# ------------------------
# BACKUP LOG - Part 2
# ------------------------
# Update the Last Successful Backup Log using run log that has just be generated.
# success_log_df dataframe may have been created in PREVIOUS BACKUP INFO
# section

# Only if backups were attempted (at least one HFS edited since last
# successful backup)
if len(backup_list) > 0:
    # Check if there is anything to update (backup status == 'success' in current run)
    s = log_df['status']=='success' 
    if True in s.values:
        # At least one successful backup to record

        if success_log_exists and (success_log_df.shape[0]>0):
            #print(success_log_df.head(1))

            # note that merging casts the timestamp columns (last_edit_date/_r) as 
            # floats if they contain NaN
            merge_df = success_log_df.merge(log_df, how = 'outer', on='item_id', suffixes=('', '_r'))

            # Select only the rows where current run last_edit_date_r is more recent
            # than success log last_edit_date (or is blank), and the backup was successful
            query = ((merge_df['last_edit_date_ts_r'] > merge_df['last_edit_date_ts'] ) | (merge_df['last_edit_date_ts'].isna())) & (merge_df['status'] == 'success')

            merge_df.loc[query,'item_name':'path'] = merge_df.loc[query,'item_name_r':'path_r'].values

            success_log_df = merge_df.loc[:,'item_id':'path']

        else:
            # Last successful backup log wasn't found, use current run log - but 
            # only successful backups (series s)
            success_log_df = log_df.loc[s,'item_id':'path']

        print("""Writing new index of successful backups to:
        """ + success_log_csv_path)
        try:
            # Write updated values out to last successful backup csv
            success_log_df.to_csv(success_log_csv_path, index = False)
        except:
            print("Unable to write success log - Open in Excel? Check permissions for the folder.")

        
############## END ##############

print("BACKUP COMPLETED")
# Pause to allow user to read print output
#time.sleep(2*60)

