########################################################################
# $Id: $
########################################################################

"""
It is a wrapper on top of Elasticsearch. It is used to manage the DIRAC monitoring types. 
"""
import datetime

from DIRAC import S_OK, S_ERROR, gConfig, gLogger
from DIRAC.Core.Base.ElasticDB import ElasticDB

from DIRAC.MonitoringSystem.private.TypeLoader import TypeLoader

__RCSID__ = "$Id$"

########################################################################
class MonitoringDB( ElasticDB ):

  def __init__( self, name = 'Monitoring/MonitoringDB', readOnly = False ):
    super( MonitoringDB, self ).__init__( 'MonitoringDB', name )
    self.__readonly = readOnly
    self.__documents = {}
    self.__loadIndexes()
           
  def __loadIndexes( self ):
    """
    It loads all monitoring indexes and types.
    """
    retVal = gConfig.getSections( "/DIRAC/Setups" )
    if not retVal[ 'OK' ]:
      return retVal
    
    setupsList = retVal[ 'Value' ]
    objectsLoaded = TypeLoader().getTypes()

    # Load the files
    for pythonClassName in sorted( objectsLoaded ):
      typeClass = objectsLoaded[ pythonClassName ]
      for setup in setupsList:
        indexName = "%s_%s" % ( setup.lower(), typeClass()._getIndex() )
        doc_type = typeClass()._getDocType() 
        mapping = typeClass().getMapping()
        monfields = typeClass().getMonitoringFields()
        self.__documents[doc_type] = {'indexName': indexName,
                                      'mapping':mapping,
                                      'monitoringFields':monfields}
        if self.__readonly:
          gLogger.info( "Read only mode is okay" )
        else:
          self.registerType( indexName, mapping )
  
  def getIndexName( self, typeName ):
    """
    :param tyeName it is a string. doc_type and type name is equivalent
    """
    indexName = None
    
    if typeName in self.__documents:
      indexName = self.__documents.get( typeName ).get( "indexName", None )
      
    if indexName:
      return S_OK( indexName )
    else:
      return S_ERROR( "Type %s is not defined" % typeName )
  
  def registerType( self, index, mapping ):
    """
    It register the type and index, if does not exists
    :param str index name of the index
    :param dict mapping mapping used to create the index.
    """ 
    
    all_index = "%s-*" % index
    
    if self.exists( all_index ):  
      indexes = self.getIndexes()
      if indexes:
        actualindexName = self._generateFullIndexName( index )
        if self.exists( actualindexName ):  
          self.log.info( "The index is exists:", actualindexName )
        else:
          result = self.createIndex( index, mapping )
          if not result['OK']:
            self.log.error( result['Message'] )
            return result
          self.log.info( "The index is created", actualindexName )
    else:
      # in that case no index exists
      result = self.createIndex( index, mapping )
      if not result['OK']:
        self.log.error( result['Message'] )
      else:
        return result
      
  
    
  def getKeyValues( self, typeName ):
    """
    Get all values for a given key field in a type
    """
    keyValuesDict = {}
    
    retVal = self.getIndexName( typeName )
    if not retVal['OK']:
      return retVal
    indexName = "%s*" % ( retVal['Value'] )
    retVal = self.getDocTypes( indexName )
    if not retVal['OK']:
      return retVal
    docs = retVal['Value']
    gLogger.debug( "Doc types", docs )
    monfields = self.__documents[typeName]['monitoringFields']
    
    if typeName not in docs:
      #this is only happen when we the index is created and we were not able to send records to the index. 
      #There is no data in the index we can not create the plot.
      return S_ERROR( "%s empty and can not retrive the Type of the index" % indexName )
    for i in docs[typeName]['properties']:
      if i not in monfields and not i.startswith( 'time' ):
        retVal = self.getUniqueValue( indexName, i )
        if not retVal['OK']:
          return retVal
        keyValuesDict[i] = retVal['Value']
    return S_OK( keyValuesDict )                                            
    
  def retrieveBucketedData( self, typeName, startTime, endTime, interval, selectFields, condDict, grouping, metainfo ):
    """
    Get data from the DB
    
    :param str typeName name of the monitoring type
    :param int startTime  epoch objects.
    :param int endtime epoch objects.
    :param dict condDict -> conditions for the query
                  key -> name of the field
                  value -> list of possible values
     
    """
    
    retVal = self.getIndexName( typeName )
    if not retVal['OK']:
      return retVal
    isAvgAgg = False
    # the data is used to fill the pie charts. This aggregation is used to average the buckets.
    if metainfo and metainfo.get( 'metric', 'sum' ) == 'avg':
      isAvgAgg = True
    
    indexName = "%s*" % ( retVal['Value'] )
    q = [self._Q( 'range',
                  timestamp = {'lte':endTime * 1000,
                          'gte': startTime * 1000} )]
    for cond in condDict:
      kwargs = {cond: condDict[cond][0]}
      query = self._Q( 'match', **kwargs )
      q += [query] 
    
    a1 = self._A( 'terms', field = grouping, size = 0 )
    a2 = self._A( 'terms', field = 'timestamp' )
    a2.metric( 'total_jobs', 'sum', field = selectFields[0] )
    a1.bucket( 'end_data',
               'date_histogram',
               field = 'timestamp',
               interval = interval ).metric( 'tt', a2 ).pipeline( 'avg_monthly_sales',
                                                                  'avg_bucket',
                                                                  buckets_path = 'tt>total_jobs',
                                                                  gap_policy = 'insert_zeros' )
    if isAvgAgg:
      a1.pipeline( 'avg_total_jobs',
                   'avg_bucket',
                   buckets_path = 'end_data>avg_monthly_sales',
                   gap_policy = 'insert_zeros' )
    
    s = self._Search( indexName )
    s = s.filter( 'bool', must = q )
    s.aggs.bucket( '2', a1 )
    s.fields( ['timestamp'] + selectFields )
    gLogger.debug( 'Query:', s.to_dict() )
    retVal = s.execute()
    
    result = {}
    for i in retVal.aggregations['2'].buckets:
      if isAvgAgg:
        result[i.key] = i.avg_total_jobs.value
      else:
        site = i.key
        dp = {}
        for j in i.end_data.buckets:
          dp[j.key / 1000] = j.avg_monthly_sales.value
        result[site] = dp
    
    return S_OK( result )
    
  def put( self, records, monitoringType ):
    """
    It is used to insert the data to El.
    :param list records it is a list of documents (dictionary)
    :param str monitoringType is the type of the monitoring
    """
    mapping = self.__getMapping( monitoringType )
    gLogger.debug( "Mapping used to create an index:", mapping )
    res = self.getIndexName( monitoringType )
    if not res['OK']:
      return res
    indexName = res['Value']
    return self.bulk_index( indexName, monitoringType, records, mapping )
  
  def __getMapping( self, monitoringType ):
    """
    It returns the mapping of a certain monitoring type
    :param str monitoringType the monitoring type for example WMSHistory
    :return it returns an empty dixtionary if there is no mapping defenied.
    """
    mapping = {}
    if monitoringType in self.__documents:
      mapping = self.__documents[monitoringType].get( "mapping", {} )
    return mapping
  
  def __getRawData( self, typeName, condDict, size = 0 ):
    """
    It returns the last day data for a given monitoring type.
    for example: {'sort': [{'timestamp': {'order': 'desc'}}], 
    'query': {'bool': {'must': [{'match': {'host': 'dzmathe.cern.ch'}}, 
    {'match': {'component': 'Bookkeeping_BookkeepingManager'}}]}}}
    :param str typeName name of the monitoring type
    :param dict condDict -> conditions for the query
                  key -> name of the field
                  value -> list of possible values
    :param int size number of rows which whill be returned. By default is all
    """
    retVal = self.getIndexName( typeName )
    if not retVal['OK']:
      return retVal
    date = datetime.datetime.utcnow()
    indexName = "%s-%s" % ( retVal['Value'], date.strftime( '%Y-%m-%d' ) )
    
    # going to create:
    # s = Search(using=cl, index = 'lhcb-certification_componentmonitoring-index-2016-09-16')
    # s = s.filter( 'bool', must = [Q('match', host='dzmathe.cern.ch'), Q('match', component='Bookkeeping_BookkeepingManager')]) 
    # s = s.query(q)
    # s = s.sort('-timestamp')
    
    
    mustClose = []
    for cond in condDict:
      kwargs = {cond: condDict[cond][0]}
      query = self._Q( 'match', **kwargs )
      mustClose.append( query ) 
    
    if condDict.get( 'startTime' ) and condDict.get( 'endTime' ):
      query = self._Q( 'range',
                timestamp = {'lte':condDict.get( 'endTime' ),
                             'gte': condDict.get( 'startTime' ) } )
      
      mustClose.append( query )
    
    s = self._Search( indexName )
    s = s.filter( 'bool', must = mustClose )
    s = s.sort( '-timestamp' )
    
    if size > 0:
      s = s.extra( size = size ) 
    
    retVal = s.execute()
    if not retVal['OK']:
      return retVal
    if retVal['Value']:
      records = []
      paramNames = dir( retVal['Value'][0] )
      try:
        paramNames.remove( 'meta' )
      except ValueError as e:
        gLogger.warn( "meta is not in the Result", e )
      for resObj in retVal["Value"]:
        records.append( dict( [ ( paramName, getattr( resObj, paramName ) ) for paramName in paramNames] ) )
      return S_OK( records )
  
  def getLastDayData( self, typeName, condDict ):
    """
    It returns the last day data for a given monitoring type.
    for example: {'sort': [{'timestamp': {'order': 'desc'}}], 
    'query': {'bool': {'must': [{'match': {'host': 'dzmathe.cern.ch'}}, 
    {'match': {'component': 'Bookkeeping_BookkeepingManager'}}]}}}
    :param str typeName name of the monitoring type
    :param dict condDict -> conditions for the query
                  key -> name of the field
                  value -> list of possible values
    """
    return self.__getRawData( typeName, condDict )
    
  
  def getLimitedData( self, typeName, condDict, size = 10 ):
    """
    Returns a list of records for a given selection.
    :param str typeName name of the monitoring type
    :param dict condDict -> conditions for the query
                  key -> name of the field
                  value -> list of possible values
    :param int size: Indicates how many entries should be retrieved from the log
    :return: Up to size entries for the given component from the database
    """
    return self.__getRawData( typeName, condDict, size )
    
  
  def getDataForAGivenPeriod( self, typeName, condDict, initialDate = '', endDate = '' ):
    """
    Retrieves the history of logging entries for the given component during a given given time period
    :param: str typeName name of the monitoring type
    :param: dict condDict -> conditions for the query
                  key -> name of the field
                  value -> list of possible values
    :param str initialDate: Indicates the start of the time period in the format 'DD/MM/YYYY hh:mm'
    :param str endDate: Indicate the end of the time period in the format 'DD/MM/YYYY hh:mm'
    :return: Entries from the database for the given component recorded between the initial and the end dates
    
    """
    if not initialDate and not endDate:
      return self.__getRawData( typeName, condDict, 10 )

    if initialDate:
      condDict['startTime'] = datetime.datetime.strptime( initialDate, '%d/%m/%Y %H:%M' )
    else:
      condDict['startTime'] = datetime.datetime.min
    if endDate:
      condDict['endTime'] = datetime.datetime.strptime( endDate, '%d/%m/%Y %H:%M' )
    else:
      condDict['endTime'] = datetime.datetime.utcnow()
      
    
    return self.__getRawData( typeName, condDict )
    
