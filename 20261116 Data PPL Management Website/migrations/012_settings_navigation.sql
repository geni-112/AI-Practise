UPDATE records
SET payload=JSON_REMOVE(payload,'$.labels.maas'),version=version+1
WHERE id='workspace-navigation-v1' AND kind='meta' AND JSON_CONTAINS_PATH(payload,'one','$.labels.maas')=1;
