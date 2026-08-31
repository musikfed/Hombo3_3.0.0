# EN: Raw PCM TCP sink compatible with the previous robot backend (PCM1 header, port 3333).
# RU: TCP-приёмник PCM совместим с прежним backend робота (заголовок PCM1, порт 3333).
import asyncio
import struct
from machine import Pin
try:
    from machine import I2S
except ImportError:
    I2S=None
from board_config import PIN_I2S_BCLK,PIN_I2S_LRCK,PIN_I2S_DOUT,AUDIO_PORT

async def read_exact(reader,n):
    out=bytearray()
    while len(out)<n:
        chunk=await reader.read(n-len(out))
        if not chunk: break
        out.extend(chunk)
    return bytes(out)

class AudioService:
    def __init__(self):
        self.active=False; self.i2s=None; self.rate=0; self.available=I2S is not None
    def _open(self,rate):
        if not self.available: return False
        if self.i2s is not None and self.rate==rate: return True
        if self.i2s is not None:
            try:self.i2s.deinit()
            except Exception:pass
        try:
            self.i2s=I2S(0,sck=Pin(PIN_I2S_BCLK),ws=Pin(PIN_I2S_LRCK),sd=Pin(PIN_I2S_DOUT),
                         mode=I2S.TX,bits=16,format=I2S.MONO,rate=rate,ibuf=20000)
            self.rate=rate; return True
        except Exception as exc:
            print("I2S unavailable:",exc); self.i2s=None; return False
    async def client(self,reader,writer):
        try:
            header=await read_exact(reader,12)
            if len(header)!=12 or header[:4]!=b"PCM1": return
            rate,size=struct.unpack("<II",header[4:12])
            if rate<8000 or rate>48000 or size>8*1024*1024 or not self._open(rate): return
            self.active=True; remaining=size
            while remaining>0:
                chunk=await reader.read(min(1024,remaining))
                if not chunk: break
                self.i2s.write(chunk); remaining-=len(chunk)
                await asyncio.sleep_ms(0)
        finally:
            self.active=False
            try: writer.close(); await writer.wait_closed()
            except Exception: pass
    async def serve(self):
        return await asyncio.start_server(self.client,"0.0.0.0",AUDIO_PORT)
