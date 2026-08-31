# EN: Optional full MicroPython core OTA. Requires dual OTA partitions.
# RU: Опциональное OTA-обновление ядра MicroPython. Требует двух OTA-разделов.
import hashlib, binascii
try:
    import esp32
except ImportError:
    esp32=None

_part=None; _size=0; _sha=""; _written=0

def status():
    if esp32 is None: return {"core_ota_available":False,"reason":"esp32.Partition unavailable"}
    try:
        running=esp32.Partition(esp32.Partition.RUNNING)
        nxt=running.get_next_update()
        info=nxt.info()
        return {"core_ota_available":True,"running":running.info()[4],"next":info[4],"next_size":info[3]}
    except Exception as exc:
        return {"core_ota_available":False,"reason":str(exc)}

def begin(size,sha256):
    global _part,_size,_sha,_written
    st=status()
    if not st.get("core_ota_available"): raise RuntimeError(st.get("reason","OTA partitions unavailable"))
    if size<=0 or size>st["next_size"]: raise ValueError("firmware image does not fit OTA partition")
    _part=esp32.Partition(esp32.Partition.RUNNING).get_next_update()
    _size=int(size); _sha=str(sha256).lower(); _written=0
    return {"ok":True,"partition":_part.info()[4],"size":_size}

def write_block(block,data):
    global _written
    if _part is None: raise RuntimeError("OTA not started")
    if len(data)%4096: raise ValueError("chunk must be 4096-byte aligned")
    _part.writeblocks(int(block),data); _written+=len(data)
    return {"ok":True,"block":int(block),"written":_written}

def finish():
    global _part
    if _part is None: raise RuntimeError("OTA not started")
    h=hashlib.sha256(); left=_size; block=0; buf=bytearray(4096)
    while left>0:
        _part.readblocks(block,buf)
        take=min(left,4096); h.update(memoryview(buf)[:take]); left-=take; block+=1
    digest=binascii.hexlify(h.digest()).decode()
    if digest.lower()!=_sha: raise ValueError("firmware sha256 verification failed")
    _part.set_boot()
    return {"ok":True,"sha256":digest,"boot_partition":_part.info()[4],"hard_reset_required":True}
