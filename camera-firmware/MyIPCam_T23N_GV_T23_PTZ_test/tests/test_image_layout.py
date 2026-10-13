#!/usr/bin/env python3
"""Validate the MyIPCam/T23N SD image layout without mounting."""
import hashlib,struct,sys
from pathlib import Path
if len(sys.argv)!=2: raise SystemExit(f"usage: {sys.argv[0]} IMAGE.bin")
data=Path(sys.argv[1]).read_bytes()
assert len(data)<=128*1024*1024,"image exceeds 128 MiB project limit"
assert data[510:512]==b"\x55\xaa","missing MBR signature"
def part(i):
 off=446+i*16; e=data[off:off+16]
 return e[4],*struct.unpack_from("<II",e,8)
p1,p2=part(0),part(1)
assert p1[1]==2048,f"unexpected p1 start: {p1[1]}"
assert p2[1]==34816,f"unexpected p2 start: {p2[1]}"
assert p2[2]==139264,f"unexpected p2 size: {p2[2]}"
assert data[0x4400:0x4404]!=b"\0"*4,"SPL area looks empty"
print("PASS: image size",len(data),"bytes")
print("PASS: p1",p1)
print("PASS: p2",p2)
print("PASS: SHA256",hashlib.sha256(data).hexdigest())
