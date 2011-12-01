Setup: 

   Before starting the follwoing procedure, you need to set SSLEAY_CONFIG
   variable.  E.g.:

      export SSLEAY_CONFIG=-config /usr/home/cslater/Head/godspeed/coroutine/coro_ssl_data/openssl.cnf

To create self-signed certificate: 
---------------------------------

Use the following command:

openssl req -new -x509 -newkey rsa:1024 -keyout demo-key.txt -out demo-cert.txt -sha1 -nodes -days 3653

This creates self-signed certificate in demo-cert.pem file and the corresponsing private key
in demo-key.pem file which are imported as default keys by coro_ssl module.

To create a Root CA certificate and then sign new certificates with it:
-----------------------------------------------------------------------

Steps for creating new demo certificate and key:

1.  ./CA.pl -newca
2.  cd demoCA
3.  ../CA.pl -newreq
4.  ../CA.pl -sign
5.  new certficate is in ./newcerts  (demoCA/newcerts)
6.  Remove decoded text from certificate (above "-----BEGIN CERTIFICATE-----")
7.  remove rsa encryption from key (openssl rsa < newreq.pem > demo-key.txt)
