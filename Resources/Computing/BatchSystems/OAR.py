#!/bin/env python

import re, sys, tempfile, commands, os, urllib, json

def submitJob( executable,outputDir,errorDir,nJobs,queue,submitOptions ):
  """ Submit nJobs to the condor batch system
  """
  outFile = os.path.join( outputDir , "%jobid%" )
  errFile = os.path.join( errorDir , "%jobid%" )
  jobIDs = []
  for i in range( int(nJobs) ):
    cmd = "oarsub -O %s.out -E %s.err -q %s -n DIRACPilot %s" % ( outFile,
                                                          errFile,
                                                          queue,
                                                          #submitOptions,
                                                          executable )
    status,output = commands.getstatusoutput(cmd)

    if status != 0:
      break

    if not len( output ) > 0:
      break

    lines = output.split( '\n' )
    if lines[ -1 ].find( "[JOB START]" ) >= 0:
        prefix , jid = lines[ -1 ].split( ":" )

    if not jid:
      break

    jid = jid.strip()
    jobIDs.append( jid )

  if jobIDs:
    print 0
    for job in jobIDs:
      print job
  else:
    print status
    print output

  return status


def killJob( jobList ):
  """ Delete a job from OAR batch scheduler. Input: list of jobs ourput: int
  """

  if not isinstance( jobList , list ):
    jobList = list ( jobList )

  result = 0
  successful = []
  failed = []

  for job in jobList:
    status,output = commands.getstatusoutput( 'oardel %s' % job )
    if status != 0:
      result += 1
      failed.append( job )
    else:
      successful.append( job )

  print result
  for job in successful:
    print job
  return result


def getJobStatus( jobs , user ):
  """ Get status of the jobs in the given list
  """

  resultDict = {}
  if not isinstance( jobs , list ):
    jobs = list ( jobs )

  status , output = commands.getstatusoutput( "oarstat --sql \"project = '%s'\" -J" % user )
  if status != 0:
    print status
    print output
    return status

  try:
    output = json.loads( output )
  except Exception , x:
    status = 2048
    print status
    print output
    return status

  if not len( output ) > 0:
    status = 1024
    print status
    print output
    return status

  for job in jobs:

    if not job in output:
      resultDict[ job ] = "Unknown"
      continue

    if not "state" in output[ job ]:
      resultDict[ job ] = "Unknown"
      continue
    state = output[ job ][ "state" ]

    if state in [ "Running", "Finishing" ]:
      resultDict[ job ] = "Running"
      continue

    if state in [ "Error", "toError" ]:
      resultDict[ job ] = "Aborted"
      continue

    if state in [ "Waiting", "Hold", "toAckReservation", "Suspended", "toLaunch", "Launching" ]:
      resultDict[ job ] = "Waiting"
      continue

    if state == "Terminated":
      resultDict[ job ] = "Done"
      continue

    resultDict[ job ] = "Unknown"
    continue

  # Final output
  status = 0
  print status
  for job,status in resultDict.items():
    print ':::'.join( [job,status] )

  return status

def getCEStatus( user ):
  """  Get the overall status of the CE
  """

  waitingJobs = 0
  runningJobs = 0

  status , output = commands.getstatusoutput( 'oarstat -u %s -J' % user )
  if status != 0:
    print status
    print output
    return status

  try:
    output = json.loads( output )
  except Exception , x:
    status = 2048
    print status
    print x
    return status

  if not len( output ) > 0:
    status = 0
    print status
    print ":::".join( ["Waiting",str(waitingJobs)] )
    print ":::".join( ["Running",str(runningJobs)] )
    return status

  for value in output.values():

    if not "state" in value:
      continue
    state = value[ "state" ]

    if state in [ "Running", "Finishing" ]:
      runningJobs += 1
      continue

    if state in [ "Waiting", "Hold", "toAckReservation", "Suspended", "toLaunch", "Launching" ]:
      waitingJobs += 1
      continue

  status = 0
  print status
  print ":::".join( ["Waiting",str(waitingJobs)] )
  print ":::".join( ["Running",str(runningJobs)] )
  return status

#####################################################################################

# Get standard arguments and pass to the interface implementation functions

command = sys.argv[1]
print "============= Start output ==============="
if command == "submit_job":
  executable,outputDir,errorDir,workDir,nJobs,infoDir,jobStamps,queue,submitOptions = sys.argv[2:]
  submitOptions = urllib.unquote(submitOptions)
  if submitOptions == '-':
    submitOptions = ''
#  status = submitJob( executable, nJobs, outputDir, submitOptions )
  status = submitJob( executable,outputDir,errorDir,nJobs,queue,submitOptions )
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
  
  