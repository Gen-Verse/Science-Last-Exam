"""Compatibility import; GUI uses the common agent and its gui tool."""
from sle.agent import ScienceAgent
from sle.tools.gui import request

class ScienceGUIAgent(ScienceAgent):
    def __init__(self,*args,**kwargs):
        kwargs['mode']='gui'
        super().__init__(*args,**kwargs)
