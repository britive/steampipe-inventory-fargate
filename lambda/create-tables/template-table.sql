CREATE EXTERNAL TABLE `#service#_#resource#_snapshots` (
#fields#
)
PARTITIONED BY (
  `inventory_snapshot` STRING
)
ROW FORMAT SERDE 'org.openx.data.jsonserde.JsonSerDe'
STORED AS INPUTFORMAT 'org.apache.hadoop.mapred.TextInputFormat'
OUTPUTFORMAT 'org.apache.hadoop.hive.ql.io.IgnoreKeyTextOutputFormat'
LOCATION 's3://#bucket#/#prefix#'
TBLPROPERTIES (
  'has_encrypted_data'='false',
  'projection.enabled'='true',
  'projection.inventory_snapshot.format'='yyyy/MM/dd',
  'projection.inventory_snapshot.interval'='1',
  'projection.inventory_snapshot.interval.unit'='DAYS',
  'projection.inventory_snapshot.range'='2021/12/01,NOW',
  'projection.inventory_snapshot.type'='date',
  'storage.location.template'='s3://#bucket#/#prefix#/${inventory_snapshot}/#service#/#resource#'
)