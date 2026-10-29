import sys, runpy
sys.argv = ["cost.py", "gate"] + sys.argv[1:]
runpy.run_path(__file__.replace("gate3.py", "cost.py"), run_name="__main__")
