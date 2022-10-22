#!/usr/bin/python
# -*- coding: utf-8 -*-

import re
#from jsbeautifier.unpackers.packer import unpack
from proxytools.packer import deobfuscate
from proxytools.crazyxor import parse_crazyxor, decode_crazyxor

js1 = "eval(function(p,a,c,k,e,d){e=function(c){return(c<a?'':e(parseInt(c/a)))+((c=c%a)>35?String.fromCharCode(c+29):c.toString(36))};if(!''.replace(/^/,String)){while(c--){d[e(c)]=k[c]||e(c)}k=[function(e){return d[e]}];e=function(){return'\\w+'};c=1};while(c--){if(k[c]){p=p.replace(new RegExp('\\b'+e(c)+'\\b','g'),k[c])}}return p}('$(r).s(t(){$(\'.q\').0(p);$(\'.m\').0(n);$(\'.o\').0(u);$(\'.v\').0(B);$(\'.C\').0(D);$(\'.A\').0(z);$(\'.w\').0(x);$(\'.y\').0(l);$(\'.k\').0(7);$(\'.8\').0(9);$(\'.6\').0(4);$(\'.1\').0(2);$(\'.5\').0(3);$(\'.a\').0(b);$(\'.h\').0(i);$(\'.j\').0(g);$(\'.f\').0(c);$(\'.d\').0(e);$(\'.E\').0(1j);$(\'.F\').0(17);$(\'.18\').0(15);$(\'.14\').0(11);$(\'.12\').0(13);$(\'.19\').0(1a);$(\'.1g\').0(1h);$(\'.1i\').0(1f);$(\'.1e\').0(1b);$(\'.1c\').0(1d);$(\'.10\').0(Z);$(\'.M\').0(N);$(\'.O\').0(L);$(\'.K\').0(G);$(\'.H\').0(I);$(\'.J\').0(P);$(\'.Q\').0(W);$(\'.X\').0(Y);$(\'.V\').0(U);$(\'.R\').0(S);$(\'.T\').0(16)});',62,82,'html|r776a|8118|3129|8081|r0515|r7641|65205|r4620|20183|r5a69|90|61234|rddb3|9999|reba4|8060|rd0d1|9000|r9c14|r6032|544|ra7c2|8080|r7f55|80|r6f9e|document|ready|function|8000|r257a|reaa3|41239|r7549|3128|r1973|8888|r33d8|53281|rdda0|r8d1f|6666|rd969|45619|rc4ca|r2951|54214|r4398|55555|r169c|8088|r1af5|r7c10|87|rdf97|443|re1ee|9090|rdad6|8980|1080|r6912|45618|r40f7|62225|r2e35|65103|6868|63909|r3a9b|r1ed6|65309|53282|r0a1b|8123|rffd8|41525|rc7de|3355|r4129|53005'.split('|'),0,{}))"
js2 = "eval(function(p,a,c,k,e,d){e=function(c){return(c<a?'':e(parseInt(c/a)))+((c=c%a)>35?String.fromCharCode(c+29):c.toString(36))};if(!''.replace(/^/,String)){while(c--){d[e(c)]=k[c]||e(c)}k=[function(e){return d[e]}];e=function(){return'\\w+'};c=1};while(c--){if(k[c]){p=p.replace(new RegExp('\\b'+e(c)+'\\b','g'),k[c])}}return p}('$(k).l(j(){$(\'.i\').0(g);$(\'.h\').0(m);$(\'.n\').0(s);$(\'.r\').0(q);$(\'.o\').0(f);$(\'.t\').0(e);$(\'.5\').0(4);$(\'.7\').0(3);$(\'.1\').0(2);$(\'.6\').0(8);$(\'.d\').0(c);$(\'.b\').0(9);$(\'.a\').0(p);$(\'.X\').0(u);$(\'.P\').0(N);$(\'.M\').0(K);$(\'.L\').0(Q);$(\'.R\').0(W);$(\'.V\').0(U);$(\'.S\').0(T);$(\'.J\').0(I);$(\'.z\').0(A);$(\'.y\').0(x);$(\'.v\').0(w);$(\'.B\').0(C);$(\'.H\').0(G);$(\'.F\').0(D);$(\'.E\').0(O)});',60,60,'html|ra79b|20183|65205|544|rfbb3|rfac9|r6277|15600|9000|rf196|r64bb|8088|rcb41|81|53281|8080|r4af4|rdbbf|function|document|ready|80|rad9e|r2907|9999|3128|rfc13|8000|r1315|62225|r3ebb|3129|52136|r3239|rcc99|53282|r4178|8090|41525|r5654|rd77c|54214|rf9ec|55555|r7712|65103|r2342|rcdcd|8888|10000|r5973|6660|re3b6|r38f1|8082|65301|rfc3a|45618|r32d4'.split('|'),0,{}))"

js3 = "eval(function(p,r,o,x,y,s){y=function(c){return(c<r?'':y(parseInt(c/r)))+((c=c%r)>35?String.fromCharCode(c+29):c.toString(36))};if(!''.replace(/^/,String)){while(o--){s[y(o)]=x[o]||y(o)}x=[function(y){return s[y]}];y=function(){return'\\w+'};o=1};while(o--){if(x[o]){p=p.replace(new RegExp('\\b'+y(o)+'\\b','g'),x[o])}}return p}('m=D^C;n=8;k=2;o=B^E;b=3;l=5;d=4;e=F^A;s=6;c=G^I;f=0;i=y^u;g=w^z;a=x^v;h=1;r=7;j=H^M;t=T^U;p=9;q=V^X;J=f^j;W=h^i;R=k^g;S=b^a;L=d^e;K=l^m;N=s^t;O=r^q;Q=n^o;P=p^c;',60,60,'^^^^^^^^^^Two3Two^Zero^Eight6Six^Six^Seven0Seven^Eight^SevenNineEight^Four^Seven9Five^Four5Nine^Two^Five^EightEightOne^One^One6Three^Nine^TwoFourFour^Three^Seven^Eight8Zero^1080^9090^10249^5003^3351^6588^8088^8836^8080^7670^8118^6359^4639^4095^81^TwoSevenFourOne^Zero2SixThree^OneTwoNineEight^3127^FourSevenThreeSix^OneThreeEightFive^EightOneTwoSeven^Nine5ZeroTwo^Eight4FiveNine^One7OneZero^6208^8909^4583^Four2SevenFour^8090'.split('\u005e'),0,{}))"
#js3 = "eval(function(p,a,c,k,e,r){e=function(c){return(c<a?'':e(parseInt(c/a)))+((c=c%a)>35?String.fromCharCode(c+29):c.toString(36))};if(!''.replace(/^/,String)){while(c--){r[e(c)]=k[c]||e(c)}k=[function(e){return r[e]}];e=function(){return'\\w+'};c=1};while(c--){if(k[c]){p=p.replace(new RegExp('\\b'+e(c)+'\\b','g'),k[c])}}return p}('m=D^C;n=8;k=2;o=B^E;b=3;l=5;d=4;e=F^A;s=6;c=G^I;f=0;i=y^u;g=w^z;a=x^v;h=1;r=7;j=H^M;t=T^U;p=9;q=V^X;J=f^j;W=h^i;R=k^g;S=b^a;L=d^e;K=l^m;N=s^t;O=r^q;Q=n^o;P=p^c;',60,60,'^^^^^^^^^^Two3Two^Zero^Eight6Six^Six^Seven0Seven^Eight^SevenNineEight^Four^Seven9Five^Four5Nine^Two^Five^EightEightOne^One^One6Three^Nine^TwoFourFour^Three^Seven^Eight8Zero^1080^9090^10249^5003^3351^6588^8088^8836^8080^7670^8118^6359^4639^4095^81^TwoSevenFourOne^Zero2SixThree^OneTwoNineEight^3127^FourSevenThreeSix^OneThreeEightFive^EightOneTwoSeven^Nine5ZeroTwo^Eight4FiveNine^One7OneZero^6208^8909^4583^Four2SevenFour^8090'.split('\u005e'),0,{}))"
js4 = "eval(function(p,r,o,x,y,s){y=function(c){return(c<r?'':y(parseInt(c/r)))+((c=c%r)>35?String.fromCharCode(c+29):c.toString(36))};if(!''.replace(/^/,String)){while(o--){s[y(o)]=x[o]||y(o)}x=[function(y){return s[y]}];y=function(){return'\\w+'};o=1};while(o--){if(x[o]){p=p.replace(new RegExp('\\b'+y(o)+'\\b','g'),x[o])}}return p}('m=D^C;n=8;k=2;o=B^E;b=3;l=5;d=4;e=F^A;s=6;c=G^I;f=0;i=y^u;g=w^z;a=x^v;h=1;r=7;j=H^M;t=T^U;p=9;q=V^X;J=f^j;W=h^i;R=k^g;S=b^a;L=d^e;K=l^m;N=s^t;O=r^q;Q=n^o;P=p^c;',60,60,'||||||||||Two3Two|Zero|Eight6Six|Six|Seven0Seven|Eight|SevenNineEight|Four|Seven9Five|Four5Nine|Two|Five|EightEightOne|One|One6Three|Nine|TwoFourFour|Three|Seven|Eight8Zero|1080|9090|10249|5003|3351|6588|8088|8836|8080|7670|8118|6359|4639|4095|81|TwoSevenFourOne|Zero2SixThree|OneTwoNineEight|3127|FourSevenThreeSix|OneThreeEightFive|EightOneTwoSeven|Nine5ZeroTwo|Eight4FiveNine|One7OneZero|6208|8909|4583|Four2SevenFour|8090'.split('|'),0,{}))"


unpacked = deobfuscate(js3)
print('Unpacked 3:')
print(unpacked)

dictx = parse_crazyxor(unpacked)
print(dictx)


unpacked = deobfuscate(js1)
print('Unpacked 1:')
print(unpacked)

unpacked = deobfuscate(js2)
print('Unpacked 2:')
print(unpacked)

matches = re.findall('\(\'\.([\w]+)\'\).html\((\d+)\)', unpacked)

print('Matches:')
for info in matches:
    print info[0] + ' - ' + info[1]
