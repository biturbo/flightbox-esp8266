#!/usr/bin/env python
# -*- coding: utf-8 -*-
#

import web
from web import form

filename = "transformation/pcasconf.ini"

urls = (
  '/', 'Index'
)

app = web.application(urls, globals())

render = web.template.render('templates/')

class Index(object):
    def GET(self):
        return render.form()

    def POST(self):
        form = web.input(name="Nobody", greet="Hello")        
        greeting = "%s, %s, %s" % (form.ICAO,form.modecsep,form.modecdet)
        #flightID = "my_Tail: '%s'" % (form.tail)
        flightICAO = "my_ICAO: '%s'" % (form.ICAO)
        flightMODECsep = "modec_sep: %s" % (form.modecsep)
        flightMODECdet = "modec_det: %s" % (form.modecdet)
        
        target = open(filename, 'w')
        target.truncate()
        target.write("[DEFAULT]")
       # target.write("\n")
       # target.write(flightID)
        target.write("\n")
        target.write(flightICAO)
        target.write("\n")        
        target.write(flightMODECsep)
        target.write("\n")
        target.write(flightMODECdet)
        target.write("\n")
        target.close()
		
        for i in range(1,10):
           print 'REBOOT',i
           #Do your code here
           time.sleep(1)
           os.system("sudo reboot")
		   
    
if __name__ == "__main__":
    app.run()

