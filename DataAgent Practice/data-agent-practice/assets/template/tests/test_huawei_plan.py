import importlib.util
from pathlib import Path
from types import SimpleNamespace as Object


spec=importlib.util.spec_from_file_location('huawei_plan',Path(__file__).resolve().parents[1]/'scripts/huawei_resources.py')
resources=importlib.util.module_from_spec(spec)
spec.loader.exec_module(resources)


def flavor(kind='dws3.0',ram=16,zones=None):
    return Object(spec_name='small-'+kind,datastore_type=kind,vcpus=4,ram=ram,available_zones=zones,
        datastores=[Object(version='9.1.stable',role='STABLE',attachments=Object(min_cn=2))],
        elastic_volume_specs=[Object(type='SSD',min_size=40)])


def test_missing_flavor_az_uses_available_service_az_and_supports_dws3():
    zones=[Object(code='la-north-2a',status='available')]
    result=resources.flavor_candidates([flavor('dws',32),flavor()],zones)
    assert result[0]['flavor']=='small-dws3.0'
    assert result[0]['az_source']=='service' and result[0]['disk_gb']==40
    assert result[0]['datastore_version']=='9.1.stable'


def test_explicit_sold_out_flavor_does_not_fall_back_to_service_availability():
    zones=[Object(code='la-north-2a',status='available')]
    sold_out=flavor(zones=[Object(code='la-north-2a',status='sellout')])
    assert resources.flavor_candidates([sold_out],zones)==[]


def test_missing_region_availability_blocks_selection():
    assert resources.flavor_candidates([flavor()],[Object(code='la-north-2a',status='unavailable')])==[]
