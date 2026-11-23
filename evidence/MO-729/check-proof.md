Ticket proof command (exit 0 on head, exit 1 on origin/main):

python3 -c "import os,sys,runpy,tempfile;os.environ['COORD_JOURNAL_DIR']=tempfile.mkdtemp();sys.path.insert(0,'coordinator/overnight');m=runpy.run_path('coordinator/overnight/selftest.py',run_name='st');m['closed_ticket_merge']();print('closed-ticket-merge ok')"
