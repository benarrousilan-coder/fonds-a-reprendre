import json,sys
d=open(sys.argv[1]).read().replace('</','<\\/')
t=open(sys.argv[2]).read().replace('__DATA__',d)
open(sys.argv[3],'w').write(t)
