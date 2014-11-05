#!/bin/env python

import re, sys, tempfile, commands, os, urllib

def submitJob( executable,outputDir,errorDir,nJobs,jobDir,queue,submitOptions ):
  """ Submit nJobs to the condor batch system
  """
  outputs = []
  for i in range( int(nJobs) ):
    cmd = "bsub -o %s -e %s -q %s -J DIRACPilot %s %s" % ( outputDir,
                                                           errorDir,
                                                           queue,
                                                           submitOptions,
                                                           executable )
    status,output = commands.getstatusoutput(cmd)
    if status == 0:
      outputs.append(output)
    else:
      break                                                         

  if outputs:
    print 0
    for output in outputs:
      match = re.search('Job <(\d*)>',output)
      if match:
        print match.groups()[0]
  else:
    print status
    print output
    
  return status

def killJob( jobList ):
  """ Kill jobs in the given list
  """
  
  result = 0
  successful = []
  failed = []
  for job in jobList:
    status,output = commands.getstatusoutput( 'bkill %s' % job )
    if status != 0:
      result += 1
      failed.append( job )
    else:
      successful.append( job )  
  
  print result
  for job in successful:
    print job
  return result
  
def getJobStatus( jobList, user ):

  print -1
  return -1
  
def getCEStatus( user ):

  print -1
  return -1

#####################################################################################

# Get standard arguments and pass to the interface implementation functions

command = sys.argv[1]
print "============= Start output ==============="
if command == "submit_job":
  executable,outputDir,errorDir,workDir,nJobs,infoDir,jobStamps,queue,submitOptions = sys.argv[2:]
  submitOptions = urllib.unquote(submitOptions)
  if submitOptions == '-':
    submitOptions = ''
  status = submitJob( executable, outputDir, errorDir, nJobs, outputDir, queue, submitOptions )
elif command == "kill_job":
  jobStamps,infoDir = sys.argv[2:]
  jobList = jobStamps.split('#')
  status = killJob( jobList )
elif command == "job_status":
  jobStamps,infoDir,user = sys.argv[2:]
  jobList = jobStamps.split('#')
  status = getJobStatus( jobList, user )  
elif command == "status_info":
  infoDir,workDir,user,queue = sys.argv[2:]
  status = getCEStatus( user )   

sys.exit(status)
