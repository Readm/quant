"""monitoring/logger.py - 结构化JSON日志"""
import logging, json, datetime
from config.settings import LOG_LEVEL
logger = logging.getLogger("quant"); logger.setLevel(getattr(logging,LOG_LEVEL,"INFO"))
class JSONF(logging.Formatter):
    def format(self, e):
        d={"ts":datetime.datetime.now().isoformat(),"level":e.levelname,"msg":e.getMessage()}
        if e.exc_info: d["exc"]=self.formatException(e.exc_info)
        return json.dumps(d)
h=logging.StreamHandler(); h.setFormatter(JSONF()); logger.addHandler(h)
def info(msg,**k):  logger.info(msg,extra=k)
def warn(msg,**k):  logger.warning(msg,extra=k)
def error(msg,**k): logger.error(msg,extra=k)
