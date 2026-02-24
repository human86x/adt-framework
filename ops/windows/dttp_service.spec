# -*- mode: python ; coding: utf-8 -*-
import os
import sys

project_root = os.getcwd()

a = Analysis(
    [os.path.join(project_root, 'adt_core', 'dttp', 'service.py')],
    pathex=[project_root],
    binaries=[],
    datas=[(os.path.join(project_root, 'adt_core'), 'adt_core'), 
        (os.path.join(project_root, 'config'), 'config'),
        (os.path.join(project_root, '_cortex'), '_cortex')
    ],
    hiddenimports=[
        'flask', 
        'requests',
        'adt_core',
        'adt_core.ads',
        'adt_core.ads.logger',
        'adt_core.ads.query',
        'adt_core.ads.crypto',
        'adt_core.ads.schema',
        'adt_core.ads.integrity',
        'adt_core.sdd',
        'adt_core.sdd.registry',
        'adt_core.sdd.tasks',
        'adt_core.sdd.validator',
        'adt_core.dttp',
        'adt_core.dttp.gateway',
        'adt_core.dttp.policy',
        'adt_core.dttp.jurisdictions',
        'adt_core.dttp.actions',
        'adt_core.dttp.config'
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='adt_dttp_service',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='adt_dttp_service',
)
