CREATE OR REPLACE VIEW #service#_#resource# AS
SELECT * FROM #service#_#resource#_snapshots WHERE inventory_snapshot = date_format(current_timestamp, '%Y/%m/%d')