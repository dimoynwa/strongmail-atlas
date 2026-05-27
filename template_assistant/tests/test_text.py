"""Tests for extract_plain_text (spec 005 T-001, T-002)."""

from template_assistant.utils.text import extract_plain_text

NFY_PASSWORD_CREATED_HTML = """
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Skrill</title>
<link rel="stylesheet" type="text/css" href="https://www.skrill.com/fileadmin/content/Emails_2015/STRONGVIEW/CSS/style.css">

</head>
<body topmargin="0" bottommargin="0" leftmargin="0" rightmargin="0" style="padding: 0px; margin: 0px;" bgcolor="#f4f4f4" >
<!-- header - start -->
<table cellpadding="0" cellspacing="0" align="center" width="100%" border="0" bgcolor="#f4f4f4" style="background-color:#f4f4f4;table-layout: fixed; margin: 0 auto;" class="w320">
<tr>
<td valign="top" align="center">
<!-----PURPLE SKRILL LOGO------->

<table class="w320" cellpadding="0" cellspacing="0" align="center" width="640" border="0" style="width: 640px;margin: auto;" bgcolor="#f4f4f4">
        <tr valign="middle">
          <td width="20" class="w15"><img src="https://www.skrill.com/fileadmin/content/Emails_2015/Master_Images/spacer.gif" width="1" height="1" alt="" title="" style="display:block;" border="0" /></td>
          <td height="60"><table cellpadding="0" cellspacing="0" align="left" border="0">
            <tr>
              <td class="padL15" style="font-family:Arial, Helvetica, sans-serif; font-size:16px; color:#862165; text-decoration:none; font-weight:bold;"><a href="https://www.SKRILL.com/en/?utm_source=strongview&utm_medium=email&utm_campaign=1914" target="_blank" style="font-family:Arial, Helvetica, sans-serif; font-size:14px; line-height:17px; color:#862165; text-decoration:none; font-weight:normal;"><img src="https://www.skrill.com/fileadmin/content/Emails_2015/STRONGVIEW/Images/Skrill.png" width="114" height="39" alt="Skrill" title="Skrill" style="display:block; font-family:Arial, Helvetica, sans-serif; font-size:14px; line-height:17px; color:#862165; text-decoration:none; font-weight:normal;" border="0" /></a></td>
            </tr>
            </table></td>
          <td><table class="h" width="400" border="0" align="right" cellpadding="0" cellspacing="0">
            <tr>
              <td align="right" class="h" style="font-family:Arial, Helvetica, sans-serif; font-size:12px; line-height:18px; color:#939598; text-align:right; font-style:italic;">View this email in <a href="##ENVIEWINBROWSERTAG##1914 eu=##_MS_ORG_ID##   #" class="" linkname="View In Browser" target="_blank" style="font-family:Arial, Helvetica, sans-serif; font-size:12px; line-height:15px; color:#939598; text-decoration:none; font-weight:normal;"><strong>your browser</strong></a></td>
            </tr>
            </table></td>
          <td class="w15" width="20"><img src="https://www.skrill.com/fileadmin/content/Emails_2015/Master_Images/spacer.gif" width="1" height="1" alt="" title="" style="display:block;" border="0" /></td>
      </tr>
    </table>
     <!-----PURPLE SKRILL LOGO END------->
<!-----GREETING SECTION OF THE BODY ------->
       
      <table  class="w320" cellpadding="0" cellspacing="0" align="center" width="640" border="0"  bgcolor="#ffffff" style="width: 640px;margin: auto;">
        <tr>
          <td><table class="w320" cellpadding="0" cellspacing="0" align="center" width="640" border="0" style="width:640px;" bgcolor="#ffffff" >
            <tr>
          <td colspan="3" height="25"><img src="https://www.skrill.com/fileadmin/content/Emails_2015/Master_Images/spacer.gif" width="1" height="1" alt="" title="" style="display:block;" border="0" /></td>
        </tr>
            <tr>
              <td width="20" class="w15"><img src="https://www.skrill.com/fileadmin/content/Emails_2015/Master_Images/spacer.gif" width="1" height="1" alt="" title="" style="display:block;" border="0" /></td>
              <td width="600" class="w290"><table class="w290" cellpadding="0" cellspacing="0" width="600" border="0">
                <tr>
                  <td align="left" style="font-family:Arial, Helvetica, sans-serif; font-size:14px; line-height:20px; color:#555555; text-align:left;">Dear  ,</td>
                </tr>
                <tr>
                  <td height="20"><img src="https://www.skrill.com/fileadmin/content/Emails_2015/Master_Images/spacer.gif" width="1" height="1" alt="" title="" style="display:block;" border="0" /></td>
                </tr>
              </table></td>
              <td width="20" class="w15"><img src="https://www.skrill.com/fileadmin/content/Emails_2015/Master_Images/spacer.gif" width="1" height="1" alt="" title="" style="display:block;" border="0" /></td>
            </tr>
          </table>
          <!-----GREETING SECTION OF THE BODY -------> 
           
           <!---- NFY_PASSWORD_CREATED 1914  #910590 ----->
            <table class="w320" cellpadding="0" cellspacing="0" align="center" width="640" border="0" style="width: 640px;margin: auto;">
              <tr>
                <td width="20" class="w15"><img src="https://www.skrill.com/fileadmin/content/Emails_2015/Master_Images/spacer.gif" width="1" height="1" alt="" title="" style="display:block;" border="0" /></td>
                <td width="600" class="w290"><table class="w290" cellpadding="0" cellspacing="0" width="100%" border="0">
                  <tr>
                    <td align="left" style="font-family:Arial, Helvetica, sans-serif; font-size:14px; line-height:20px; color:#555555; text-align:left;">
You have successfully created a password for your Skrill account.</td>
                  </tr>
                  <tr>
                    <td height="20"><img src="https://www.skrill.com/fileadmin/content/Emails_2015/Master_Images/spacer.gif" width="1" height="1" alt="" title="" style="display:block;" border="0" /></td>
                  </tr>
                </table></td>
                <td width="20" class="w15"><img src="https://www.skrill.com/fileadmin/content/Emails_2015/Master_Images/spacer.gif" width="1" height="1" alt="" title="" style="display:block;" border="0" /></td>
              </tr>
            </table>
            
            <table class="w320" cellpadding="0" cellspacing="0" align="center" width="640" border="0" style="width: 640px;margin: auto;">
              <tr>
                <td width="20" class="w15"><img src="https://www.skrill.com/fileadmin/content/Emails_2015/Master_Images/spacer.gif" width="1" height="1" alt="" title="" style="display:block;" border="0" /></td>
                <td width="600" class="w290"><table class="w290" cellpadding="0" cellspacing="0" width="100%" border="0">
                  <tr>
                    <td align="left" style="font-family:Arial, Helvetica, sans-serif; font-size:14px; line-height:20px; color:#555555; text-align:left;">

If you did not authorise this change, please contact the <a target="_blank" style="color:#910590; text-decoration:underline;" href="https://www.SKRILL.com/contact-us/?utm_source=strongview&utm_medium=email&utm_campaign=1914">Skrill Help Team</a>.
</td>
                  </tr>
                  <tr>
                    <td height="20"><img src="https://www.skrill.com/fileadmin/content/Emails_2015/Master_Images/spacer.gif" width="1" height="1" alt="" title="" style="display:block;" border="0" /></td>
                  </tr>
                </table></td>
                <td width="20" class="w15"><img src="https://www.skrill.com/fileadmin/content/Emails_2015/Master_Images/spacer.gif" width="1" height="1" alt="" title="" style="display:block;" border="0" /></td>
              </tr>
            </table>
            
                     
<table class="w320" cellpadding="0" cellspacing="0" align="center" width="640" border="0" style="width: 640px;margin: auto;">
              <tr>
                <td width="20" class="w15"><img src="https://www.skrill.com/fileadmin/content/Emails_2015/Master_Images/spacer.gif" width="1" height="1" alt="" title="" style="display:block;" border="0" /></td>
                <td width="600" class="w290"><table class="w290" cellpadding="0" cellspacing="0" width="100%" border="0">
                  <tr>
                    <td align="left" style="font-family:Arial, Helvetica, sans-serif; font-size:14px; line-height:20px; color:#555555; text-align:left;">Best Regards,
</td>
                  </tr>
                  <tr>
                    <td height="20"><img src="https://www.skrill.com/fileadmin/content/Emails_2015/Master_Images/spacer.gif" width="1" height="1" alt="" title="" style="display:block;" border="0" /></td>
                  </tr>
                </table></td>
                <td width="20" class="w15"><img src="https://www.skrill.com/fileadmin/content/Emails_2015/Master_Images/spacer.gif" width="1" height="1" alt="" title="" style="display:block;" border="0" /></td>
              </tr>
            </table>
            
            <table class="w320" cellpadding="0" cellspacing="0" align="center" width="640" border="0" style="width: 640px;margin: auto;">
              <tr>
                <td width="20" class="w15"><img src="https://www.skrill.com/fileadmin/content/Emails_2015/Master_Images/spacer.gif" width="1" height="1" alt="" title="" style="display:block;" border="0" /></td>
                <td width="600" class="w290"><table class="w290" cellpadding="0" cellspacing="0" width="100%" border="0">
                  <tr>
                    <td align="left" style="font-family:Arial, Helvetica, sans-serif; font-size:14px; line-height:20px; color:#555555; text-align:left;">Skrill
</td>
                  </tr>
                  <tr>
                    <td height="20"><img src="https://www.skrill.com/fileadmin/content/Emails_2015/Master_Images/spacer.gif" width="1" height="1" alt="" title="" style="display:block;" border="0" /></td>
                  </tr>
                </table></td>
                <td width="20" class="w15"><img src="https://www.skrill.com/fileadmin/content/Emails_2015/Master_Images/spacer.gif" width="1" height="1" alt="" title="" style="display:block;" border="0" /></td>
              </tr>
            </table>
            

 <!-----GENERAL FOOTER FOR SKRILL LTD------->


        
    <!-- closing table here//-->
</td></tr></table>
<!-- end closing table here//-->

<table class="w320" cellpadding="0" cellspacing="0" align="center" width="640" border="0" style="background-color: #f4f4f4; width: 640px; margin: auto;" >

        <tr>

          <td><table class="w320" cellpadding="0" cellspacing="0" align="center" width="640" border="0" style="width:640px;" >

            <tr>

              <td width="20" class="w15"><img src="https://www.skrill.com/fileadmin/content/Emails_2015/Master_Images/spacer.gif" width="1" height="1" alt="" title="" style="display:block;" border="0" /></td>

              <td width="600" class="w290"><table cellpadding="0" cellspacing="0" align="center" width="100%" border="0">

                <tr>

                  <td style="font-size:1px; line-height:0px;" height="1" ><img src="https://www.skrill.com/fileadmin/content/Emails_2015/Master_Images/spacer.gif" width="1" height="1" alt="" title="" style="display:block;" border="0" /></td>

                </tr>  <tr>

                  <td style="font-size:1px; line-height:0px;" height="15" class="h15"><img src="https://www.skrill.com/fileadmin/content/Emails_2015/Master_Images/spacer.gif" width="1" height="1" alt="" title="" style="display:block;" border="0" /></td>

                </tr>
                   <tr>
                                    <td width="600" class="w290">
                                      <table cellpadding="0" cellspacing="0" align="center" width="100%" border="0">
                                        <tr>
                                          <th style="font-weight:normal;" class="wr">
                                            <!------ SKRILL FOOTER NAVIGATION LINKS ------>                 
                                            <table cellpadding="0" cellspacing="0" align="center" width="469" border="0" style="width: 469px;" class="w290">
                                              <tr>
                                                <td align="left" style="font-family:Arial, Helvetica, sans-serif; font-size:8px; line-height:16px; color:#939598; text-align:left; font-weight:normal;">
                                                 <a href="##PARAM_CUST_ACC_URL##/login?locale=en&utm_source=strongview&utm_medium=email&utm_campaign=1914&utm_content=##Campaign_Name##" target="_blank" style="font-family:Arial, Helvetica, sans-serif; font-size:11px; line-height:16px; color:#939598; text-align:left; font-weight:normal;"><strong>My Account </strong></a> &nbsp;|&nbsp;<a href="https://www.SKRILL.com/support/?utm_source=strongview&utm_medium=email&utm_campaign=1914" target="_blank" style="font-family:Arial, Helvetica, sans-serif; font-size:11px; line-height:16px; color:#939598; text-align:left; font-weight:normal;"><strong> Help</strong></a> &nbsp;|&nbsp; <a href="https://www.SKRILL.com/privacy/?utm_source=strongview&utm_medium=email&utm_campaign=1914" target="_blank" style="font-family:Arial, Helvetica, sans-serif; font-size:11px; line-height:16px; color:#939598; text-align:left; font-weight:normal;"><strong>Privacy</strong></a> &nbsp;|&nbsp; <a href="https://www.SKRILL.com/phishing/?utm_source=strongview&utm_medium=email&utm_campaign=1914" target="_blank" style="font-family:Arial, Helvetica, sans-serif; font-size:11px; line-height:16px; color:#939598; text-align:left; font-weight:normal;"><strong>Staying Safe Online</strong></a>
                                                </td>
                                              </tr>
                                            </table>
                                            <!------ SKRILL FOOTER NAVIGATION LINKS END------> 
                                          </th>
                                          <th style="font-size:1px; line-height:0px;width: 20px; height: 15px;font-weight:normal;" height="15" class="wr" width="20"><img src="https://www.skrill.com/fileadmin/content/Emails_2015/Master_Images/spacer.gif" width="1" height="1" alt="" title="" style="display:block;" border="0" /></th>
                                          <!------ POWERED BY PAYSAFE LOGO ------>
                                          <th style="font-weight:normal;"  class="wr" align="left">
                                            <table cellpadding="0" cellspacing="0" border="0">
                                              <tr>
                                                <td style="font-family:Arial, Helvetica, sans-serif; font-size:16px; color:#862165; text-decoration:none; font-weight:bold;"><img src="https://www.skrill.com/fileadmin/content/Emails_2015/STRONGVIEW/Powered_By_Paysafe_Footer_110.png" width="110" height="39" alt="Skrill" title="Skrill" style="display:block; font-family:Arial, Helvetica, sans-serif; font-size:14px; line-height:17px; color:#862165; text-decoration:none; font-weight:normal;" border="0" /></td>
                                              </tr>
                                            </table>
                                          </th>
                                          <!------ POWERED BY PAYSAFE LOGO END------>
                                        </tr>
                                      </table>
                                    </td>
                                  </tr>
  <tr>

                  <td style="font-size:1px; line-height:0px;" height="15" class="h15"><img src="https://www.skrill.com/fileadmin/content/Emails_2015/Master_Images/spacer.gif" width="1" height="1" alt="" title="" style="display:block;" border="0" /></td>

                </tr>
                
                 <tr>

                  <td align="left" style="font-family:Arial, Helvetica, sans-serif; font-size:11px; line-height:16px; color:#939598; text-align:left; font-weight:normal; font-style:italic;">

 Copyright © 2026 Skrill Limited. Skrill  is a registered trademark of Skrill  Ltd. All rights reserved.<br/><br/> 
  Skrill Limited is registered in England and Wales with company number 04260907 and its registered office is at 2 Gresham Street, London EC2V 7AD. Authorised and regulated by the Financial Conduct Authority under the Electronic Money Regulations 2011 (FRN: 900001) for the issuance of electronic money.<br/><br/>  We use cookies and similar technology in some of our emails which contain hyperlinks, each of which has a unique tag. They help us to understand a little bit about how you interact with our emails, and are used to improve our future email communications to you. If you click on links contained in this email it will allow us to track your use of our website. For more information about our use of cookies and similar technology please see our <a href="https://www.paysafe.com/paysafegroup/cookie-policy/"  target="_blank" style="color:#910590; text-decoration:underline" >Cookies Notice</a>.<br/><br/> In accordance with relevant Data Protection and Privacy laws, Paysafe is committed to protecting your privacy. If you wish to know more, please access our <a href="https://www.SKRILL.com/privacy/?utm_source=strongview&utm_medium=email&utm_campaign=1914" target="_blank" style="color:#910590; text-decoration:underline">Privacy Policy</a>.
   
</td>

                </tr>

  
                
               
                <tr>

                  <td style="font-size:1px; line-height:0px;" height="15" class="h15"><img src="https://www.skrill.com/fileadmin/content/Emails_2015/Master_Images/spacer.gif" width="1" height="1" alt="" title="" style="display:block;" border="0" /></td>

                </tr></table></td>

              <td width="20" class="w15"><img src="https://www.skrill.com/fileadmin/content/Emails_2015/Master_Images/spacer.gif" width="1" height="1" alt="" title="" style="display:block;" border="0" /></td>

            </tr>

          </table></td>

        </tr>

      </table>



           <table class="w320" cellpadding="0" cellspacing="0" align="center" width="640" border="0" style="background-color: #f4f4f4;width: 640px; margin: auto;">

        <tr>

          <td><table class="w320" cellpadding="0" cellspacing="0" align="center" width="640" border="0" style="width:640px;">

            <tr>

              <td width="20" class="w15"><img src="https://www.skrill.com/fileadmin/content/Emails_2015/Master_Images/spacer.gif" width="1" height="1" alt="" title="" style="display:block;" border="0" /></td>

              <td width="600" class="w290"><table cellpadding="0" cellspacing="0" align="center" width="100%" border="0">

                <tr>

                  <td style="font-size:1px; line-height:0px;" height="1" ><img src="https://www.skrill.com/fileadmin/content/Emails_2015/Master_Images/spacer.gif" width="1" height="1" alt="" title="" style="display:block;" border="0" /></td>

                </tr>

                <tr>

                  <td align="left" style="font-family:Arial, Helvetica, sans-serif; font-size:11px; line-height:16px; color:#939598; text-align:left; font-weight:normal; font-style:italic;">To ensure that Skrill emails reach your inbox, please add <a href="mailto:no-reply@email.SKRILL.com" style="font-family:Arial, Helvetica, sans-serif; font-size:11px; line-height:16px; color:#939598; text-align:left; font-weight:normal; text-decoration:none;"><strong>no-reply@email.SKRILL.com</strong></a> to your email safe list. </td>

                </tr>

                <tr>

                  <td style="font-size:1px; line-height:0px;" height="15" class="h10"><img src="https://www.skrill.com/fileadmin/content/Emails_2015/Master_Images/spacer.gif" width="1" height="1" alt="" title="" style="display:block;" border="0" /></td>

                </tr>

              </table></td>

              <td width="20" class="w15"><img src="https://www.skrill.com/fileadmin/content/Emails_2015/Master_Images/spacer.gif" width="1" height="1" alt="" title="" style="display:block;" border="0" /></td>

            </tr>

          </table></td>

        </tr>

      </table>
<!-----GENERAL FOOTER FOR SKRILL LTD END-------> 
<span style="font-size: 6px; color: #f4f4f4;margin: auto;">NFY_PASSWORD_CREATED 1914</span>

</td></tr></table>
<img src="https://www.google-analytics.com/collect?v=1&t=event&tid=UA-39489651-1&cid=123456789.123456789&ec=email&ea=open&sc=end&el=1914"/>
 

</body>
</html>
"""

NFY_SM_REGISTERED_HTML = """
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html lang="en" xmlns="http://www.w3.org/1999/xhtml" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">
<head>
<meta charset="utf-8"> 
<meta name="viewport" content="width=device-width"> 
<meta http-equiv="X-UA-Compatible" content="IE=edge">
<meta name="x-apple-disable-message-reformatting">
<meta name="format-detection" content="telephone=no,address=no,email=no,date=no,url=no"> <!-- Tell iOS not to automatically link certain text strings. -->
<title>Skrill</title> 

<link href="https://fonts.googleapis.com/css?family=Oswald&display=swap" rel="stylesheet">


<!-- Desktop Outlook chokes on web font references and defaults to Times New Roman, so we force a safe fallback font. -->
<!--[if mso]>
  <style>
     * {
        font-family: sans-serif !important;
       }
   </style>
<![endif]-->

   
<!--[if !mso]><!-->
<!-- insert web font reference, eg: <link href=\'https://fonts.googleapis.com/css?family=Roboto:400,700\' rel=\'stylesheet\' type=\'text/css\'> -->

<link href="https://fonts.googleapis.com/css?family=Oswald:600,800" rel="stylesheet" type="text/css"/>

<!--<![endif]-->

<!--[if mso]>
<style type="text/css">
body, table, td, a {font-family: Arial, Helvetica, sans-serif !important;}
span {font-size: 30px !important; line-height: 30px !important;
</style>
<![endif]-->
   
<!-- Web Font / @font-face : END -->

<!--  Makes background images in 72ppi Outlook render at correct size. -->
  <!--[if gte mso 9]>
  <xml>
      <o:OfficeDocumentSettings>
            <o:AllowPNG/>
            <o:PixelsPerInch>96</o:PixelsPerInch>
      </o:OfficeDocumentSettings>
</xml>
<![endif]-->

<!-- Progressive Enhancements : BEGIN -->

<!-- CSS BEGIN -->


<style>
/* Remove spaces around the email design added by some email clients. */
/* Beware: It can remove the padding / margin and add a background color to the compose a reply window. */

html,
body {
  margin: 0 !important;
  padding: 0 !important;
  height: 100% !important;
  width: 100% !important;
}


/* Stops email clients resizing small text. */

* {
  -ms-text-size-adjust: 100%;
  -webkit-text-size-adjust: 100%;
}


/* Centers email on Android 4.4 */

div[style*="margin: 16px 0"] {
  margin: 0 !important;
}


/* Stops Outlook from adding extra spacing to tables. */

table,
td {
  mso-table-lspace: 0pt !important;
  mso-table-rspace: 0pt !important;
}


/*  Replaces default bold style. */

th {
  font-weight: normal;
}


/*  Fixes webkit padding issue. */

table {
  border-spacing: 0 !important;
  border-collapse: collapse !important;
}


/*  Prevents Windows 10 Mail from underlining links despite inline CSS. Styles for underlined links should be inline. */

a {
  text-decoration: none;
}

a:visited {
  color: #910590;
}

/*  Uses a better rendering method when resizing images in IE. */

img {
  -ms-interpolation-mode: bicubic;
}


/*  A work-around for email clients meddling in triggered links. */

a[x-apple-data-detectors],

/* iOS */

.unstyle-auto-detected-links a,
.aBn {
  border-bottom: 0 !important;
  cursor: default !important;
  color: inherit !important;
  text-decoration: none !important;
  font-size: inherit !important;
  font-family: inherit !important;
  font-weight: inherit !important;
  line-height: inherit !important;
}


/*  Prevents Gmail from changing the text color in conversation threads. */

.im {
  color: inherit !important;
}


/*  Prevents Gmail from displaying a download button on large, non-linked images. */

.a6S {
  display: none !important;
  opacity: 0.01 !important;
}


/* If the above doesn\'t work, add a .g-img class to any image in question. */

img.g-img+div {
  display: none !important;
}


/*  Removes right gutter in Gmail iOS app: https://github.com/TedGoas/Cerberus/issues/89  */
/* Create one of these media queries for each additional viewport size you\'d like to fix */

/* Media Queries 580px*/
@media only screen and (max-width:580px) {

/* Customer Table Styling */
  table.main_table td {
    border-top: solid 0px #eeeeee !important;
    border-bottom: solid 0px #eeeeee !important;
  }
  table.main_table th {
    border-bottom: solid 0px #eeeeee !important;
  }
  table.main_table_2#Value-col th {
    border-bottom: solid 0px #ffffff !important;
  }
  #Value-col {
    border-bottom: solid 0px #ffffff !important;
  }
/* End Customer Table Styling */

  .autoh {height: auto !important;}
  .gmailfix-h {display: none; display: none!important; }
  .full_width {width: 100% !important;}
  *[class].h {display: none !important;}
  *[class].wr {display: block !important;}
  *[class].w100pc {width: 100% !important;}
  *[class].w320 {width: 320px !important;}
  *[class].w20 {width: 20px !important;}
  *[class].w30 {width: 30px !important;}
  .bg-hero-resize {
    background-image: url(https://www.skrill.com/fileadmin/content/Emails_2015/STRONGVIEW/Images/Mobile_Hero_2.jpg) !important;
    background-size: cover!important;
    width: 100% !important;
    height: auto !important;
  }

  .insert-div {
    border-bottom: solid 1px #D3D3D3;
  }
  .header-bg-change {
    background-color: #5c2358 !important;
  }
  .footer-bg-change {
    background-color: #4b4558 !important;
  }
  div>u~div .show-fallback {
    display: block !important;
  }
  /*Display Items in Mobile*/
  *[class].mob-reveal {
    width: 100% !important;
    display: block !important;
    height: auto !important;
    max-height: none !important;
    line-height: normal !important;
    font-size: 12px !important;
    visibility: visible !important;

    overflow: visible !important;
  }
  body[data-outlook-cycle] .oa {
    display: block !important;
  }
  body[data-outlook-cycle] .oa-hide {
    display: none !important
  }
  /*BURGER STYLES*/
  img {
    /* Allow smoother rendering of resized image in Internet Explorer */
    -ms-interpolation-mode: bicubic;
  }
  /* force styles of client inserted tel anchors */
  a[href^=tel] {
    color: #295AA6;
    font-weight: bold;
  }
  @media screen {
    @font-face {
      font-family: \'Arial, Helvetica, sans-serif\';
      font-style: normal;
      font-weight: 400;
      ;
    }
    @font-face {
      font-family: \'Arial, Helvetica, sans-serif;\';
      font-style: normal;
      font-weight: 700;
      ;
    }
    @font-face {
      font-family: \'Arial, Helvetica, sans-serif;\';
      font-style: normal;
      font-weight: 700;
      ;
    }
  }
  @media all and ( max-width: 600px) {
    *[id]#wrapper+table,
    *[class].container,
    *[class].menu {
      min-width: 0 !important;
      -moz-text-size-adjust: none;
      -ms-text-size-adjust: none;
      -webkit-text-size-adjust: none;
      width: 100% !important;
    }
    *[id]#logo {
      height: 58px;
      width: 119px;
    }
    *[id]#skrill-logo-burger {
      box-sizing: content-box;
      background-image: url("https://www.skrill.com/fileadmin/content/Emails_2015/Master_Images/SERVICE_EMAIL_IMAGES/Skrill_Logo.png");
      width: 124px;
      height: 58px;
      display: block !important;
      float: left;
      background-repeat: no-repeat;
    }
    *[id]#powered-paysafe-logo-burger {
      box-sizing: content-box;
      background-image: url("https://www.skrill.com/fileadmin/content/Emails_2015/STRONGVIEW/Images/powered_by_paysafe_white.png");
      width: 110px;
      height: 39px;
      display: block !important;
      float: left;
      background-repeat: no-repeat;
    }
    /*The burger button*/
    /*Top Burger Menu*/
    *[id]#mobile-label {
      box-sizing: content-box;
      background-color: #67235e;
      cursor: pointer;
      display: block !important;
      float: right;
      padding: 20px;
      -webkit-tap-highlight-color: transparent;
      width: 26px;
    }
    *[id]#mobile-label>b {
      background-color: #ffffff;
      -moz-border-radius: 2px;
      -webkit-border-radius: 2px;
      border-radius: 2px;
      display: block;
      height: 4px;
    }
    *[id]#mobile-label>b+b {
      margin-top: 4px;
    }
    *[class].menu td {
      padding: 0 !important;
    }
    /*Footer Burger Menu*/
    *[id]#mobile-label-footer {
      box-sizing: content-box;
      background-color: #544c63;
      cursor: pointer;
      display: block !important;
      float: right;
      padding: 20px;
      -webkit-tap-highlight-color: transparent;
      width: 26px;
    }
    *[id]#mobile-label-footer>b {
      background-color: #ffffff;
      -moz-border-radius: 2px;
      -webkit-border-radius: 2px;
      border-radius: 2px;
      display: block;
      height: 4px;
    }
    *[id]#mobile-label-footer>b+b {
      margin-top: 4px;
    }
    *[class].menu td {
      padding: 0 !important;
    }
    /*Top Burger Menu Wrapper*/
    *[id]#menu-wrapper {
      background-color: #67235e;
      max-height: 0;
      overflow: hidden;
      -moz-transition: max-height .25s linear;
      -ms-transition: max-height .25s linear;
      -o-transition: max-height .25s linear;
      -webkit-transition: max-height .25s linear;
      transition: max-height .25s linear;
    }
    *[id]#mobile-checkbox:checked+table #menu-wrapper {
      max-height: 232px;
    }
    /*Footer Burger Menu Wrapper*/
    *[id]#menu-wrapper-footer {
      background-color: #4b4558;
      max-height: 0;
      overflow: hidden;
      -moz-transition: max-height .25s linear;
      -ms-transition: max-height .25s linear;
      -o-transition: max-height .25s linear;
      -webkit-transition: max-height .25s linear;
      transition: max-height .25s linear;
    }
    *[id]#mobile-checkbox1:checked+table #menu-wrapper-footer {
      max-height: 232px;
    }
    *[class].menu+.menu {
      border-top: 1px solid #FFFFFF;
    }
    *[class].menu-item {
      color: #FFFFFF !important;
      display: block;
      padding: 12px;
      text-align: center;
    }
    *[id]#hero {
      font-size: 14px !important;
      height: auto !important;
      min-height: 50px !important;
      width: 100% !important;
    }
    td[class].content {
      padding-left: 10px !important;
      padding-right: 10px !important;
    }
    *[class].mobile-hide {
      display: none;
    }
  }
}


/* iPhone 4, 4S, 5, 5S, 5C, and 5SE */

@media only screen and (min-device-width: 320px) and (max-device-width: 374px) {
  u~div .email-container {
    min-width: 320px !important;
  }
}


/* iPhone 6, 6S, 7, 8, and X */

@media only screen and (min-device-width: 375px) and (max-device-width: 413px) {
  u~div .email-container {
    min-width: 375px !important;
  }
}


/* iPhone 6+, 7+, and 8+ */

@media only screen and (min-device-width: 414px) {
  u~div .email-container {
    min-width: 414px !important;
  }
}

</style>

<style>
/*  Hover styles for buttons */

.button-td,
.button-a {
  transition: all 100ms ease-in;
}

.button-td-primary:hover,
.button-a-primary:hover {
  background: #555555 !important;
  border-color: #555555 !important;
color:  #E7E7E7 !important;
}


/* Media Queries 600px*/

@media screen and (max-width: 600px) {
  .f38 {font-size: 38px !important; line-height: 48px !important;}
  .f40 {font-size: 40px !important; line-height: 50px !important;}
  .insert-div {
    border-bottom: solid 1px #D3D3D3;
  }
  .footer-bg-change {
    background-color: #4b4558 !important;
  }
  div>u~div .show-fallback {
    display: block !important;
  }
  .email-container {
    width: 100% !important;
    margin: auto !important;
  }
  /*  Forces table cells into full-width rows. */
  .stack-column,
  .stack-column-center {
    display: block !important;
    width: 100% !important;
    max-width: 100% !important;
    direction: ltr !important;
  }
  /* And center justify these ones. */
  .text-center {
    text-align: center !important;
  }
  .fw {
    width: 100% !important;
    max-width: 100% !important;
  }
  .stack-items {
    display: block !important;
  }
  .table-padding {
    padding: 20px 10px !important;
  }
  /*  Generic utility class for centering. Useful for images, buttons, and nested tables. */
  .center-on-narrow {
    text-align: center !important;
    display: block !important;
    margin-left: auto !important;
    margin-right: auto !important;
    float: none !important;
  }
  table.center-on-narrow {
    display: inline-block !important;
  }
  /*  Adjust typography on small screens to improve readability */
  .email-container p {
    font-size: 17px !important;
  }
}

</style>
    <!-- Progressive Enhancements : END -->
</head>

<body width="100%" style="margin: 0; padding: 0 !important; mso-line-height-rule: exactly; background-color: #ebeff0;">
<center style="width: 100%; background-color: #ebeff0;">
        <!--[if mso | IE]>
        <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #ebeff0;">
          <tr>
            <td>
              <![endif]-->
              <!-- Create white space after the desired preview text so email clients don’t pull other distracting text into the inbox preview. Extend as necessary. -->
              <!-- Preview Text Spacing Hack : BEGIN -->
              <div style="display: none; font-size: 1px; line-height: 1px; max-height: 0px; max-width: 0px; opacity: 0; overflow: hidden; mso-hide: all; font-family: sans-serif;">
                &zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;
              </div>
              <!-- Preview Text Spacing Hack : END -->
              <!-- Email Body : BEGIN -->
              <table align="center" role="presentation" cellspacing="0" cellpadding="0" border="0" width="640" style="margin: auto;" class="email-container">

                <tr>
                  <td class="h gmailfix-h oa-hide">
                    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                      <tr>
                        <td align="right" style="padding: 5px; font-family: sans-serif; font-size: 11px; line-height: 15px; color: #485161;">
                          <a href="##ENVIEWINBROWSERTAG##1914 eu=##_MS_ORG_ID##   #" target="_blank" style="font-family:Arial;font-size:11px;line-height:19px;color:#485161;text-align:right;text-decoration:none;" class="f9">View In Browser</a>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
<!-- Header Logo -->
                    <tr>
                <td valign="middle" style="text-align: center; background-image: url(\'https://www.skrill.com/fileadmin/content/Emails_2015/STRONGVIEW/Images/SkrillHeader_BG.png\'); background-color: #222222; background-position: center center !important; background-size: cover !important;" class="h oa">
                  <!--[if gte mso 9]>
                  <v:rect xmlns:v="urn:schemas-microsoft-com:vml" fill="true" stroke="false" style="width:640px;height:50px; background-position: center center !important;">
                    <v:fill type="tile" src="https://www.skrill.com/fileadmin/content/Emails_2015/STRONGVIEW/Images/SkrillHeader_BG.png" color="#222222" />
                    <v:textbox inset="0,0,0,0">
                      <![endif]-->
                      <div>
                        <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" height="50" style="height: 50px;" class="header-bg-change">
                          <tr>
                            <td valign="top" align="left" width="124" style="width: 124px;">
                              <a href="https://www.SKRILL.com/en/?utm_source=strongview&utm_medium=email&utm_campaign=1914" target="_blank"><img src="https://www.skrill.com/fileadmin/content/Emails_2015/STRONGVIEW/Images/SkrillHeader_logo_01.png" width="125" height="50"  alt="Skrill" border="0" style="display: block;"></a>
                            </td>
                            <td align="center">
                              <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" height="50">
                                <tr>
                                  <td align="right" valign="middle">
                                    <!---CTA TABLE--->
                                    <table role="presentation" cellspacing="0" cellpadding="0" border="0" class="center-on-narrow">
                                      <tr>
                                        <td class="button-td button-td-primary" style="-moz-border-radius: 8px; -webkit-border-radius: 8px; border-radius: 8px;">
                                          <a href="##PARAM_CUST_ACC_URL##/login?locale=en&utm_source=strongview&utm_medium=email&utm_campaign=1914&utm_content=##Campaign_Name##" target="_blank" class="button-a button-a-primary" style="border: 2px solid #ffffff; font-family: Arial, sans-serif; font-size: 10px; line-height: 15px; text-decoration: none; padding: 6px 22px; color: #ffffff; display: block; -moz-border-radius: 8px; -webkit-border-radius: 8px; border-radius: 8px;font-weight: bold;font-stretch: extra-condensed">LOG IN</a>
                                        </td>
                                      </tr>
                                    </table>
                                    <!---CTA TABLE end--->
                                  </td>
                                </tr>
                              </table>
                            </td>
                            <td width="30" style="font-size:1px; line-height:1px; width: 30px;" class="h w5">&nbsp;
                            </td>
                          </tr>
                        </table>
                      </div>
                      <!--[if gte mso 9]>
                    </v:textbox>
                  </v:rect>
                  <![endif]-->
                </td>
                </tr>
                <!-- Header Logo Module End -->
#592357
<!-- Background Image with Text : BEGIN -->
                <tr>
                  <!-- Bulletproof Background Images c/o https://backgrounds.cm -->
                  <td valign="middle" style="text-align: center; background-image: url(\'https://www.skrill.com/fileadmin/content/Emails_2015/STRONGVIEW/Images/FULL_BG_HERO.png\'); background-color: #5c235a; background-position: center center !important; background-size: cover !important;" class="bg-hero-resize" bgcolor="#5c235a">
                    <!--[if gte mso 9]>
                    <v:rect xmlns:v="urn:schemas-microsoft-com:vml" fill="true" stroke="false" style="width:640; background-position: center center !important;">
                      <v:fill type="tile" src="https://www.skrill.com/fileadmin/content/Emails_2015/STRONGVIEW/Images/Hero_2.png" color="#5c235a" />
                      <v:textbox  style="mso-fit-shape-to-text:true" inset="0,0,0,0">
                        <![endif]-->
                        <div>
                          <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">
                            <tr>
                              <td width="35" style="font-size:1px; line-height:1px;width: 35px;" class="w30">&nbsp;</td>
                              <td valign="top">
                                <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">
                                  <tr>
                                    <td height="45" style="height: 45px;">&nbsp;</td>
                                  </tr>
                                  <tr>
                                    <td valign="top" align="center" style="font-style:normal; font-family:  Arial, sans-serif, Georgia, Helvetica; font-size: 18px; line-height: 25px; color: #FFFFFF; text-align: left;" class="f20">Hi ,</td>
                                  </tr>
                                  <tr>
                                    <td width="1" height="20" style="height: 20px;" >&nbsp;</td>
                                  </tr>
                                  <tr>



                                    <td valign="top" align="center" style=" font-family: \'Oswald\', sans-serif, Arial, sans-serif, Arial Black; font-size: 41px; line-height: 54px; color: #ffffff; text-align: left; font-stretch: extra-condensed;mso-ansi-font-size: 26px !important;" class="f38 MSO_hero">

                                                  <span><strong>YOU JUST SENT</strong></span>
                                    </td>
                                  </tr>
                                  <tr>
                                    <td width="1" height="20" style="height: 20px;" >&nbsp;</td>
                                  </tr>
                                  <tr>
                                    <td valign="top" align="center" style="font-style:normal; font-family:  Arial, sans-serif, Georgia, Helvetica; font-size: 20px; line-height: 25px; color: #FFFFFF; text-align: left;" class="f20 gmail-w">
                                      ##CURRENCY## ##AMOUNT## to ##RECIPIENT_NAME##.
                                    </td>
                                  </tr>
                                  <tr>
                                    <td width="1" height="20" style="height: 20px;" >&nbsp;</td>
                                  </tr>
                                  <tr>
                                    <td align="center">
                                      <!---CTA TABLE--->
                                      <table width="100%" border="0" cellspacing="0" cellpadding="0" style="width:100%;">
                                        <tr>
                                          <td>
                                            <img alt="spacer" src="https://www.skrill.com/fileadmin/content/Emails_2015/Modular_Templates/spacer.gif" width="1" height="20" style="display: block;" class="w5">
                                          </td>
                                          <td >
                                            <!----CTA---->
                                            <table align="left" role="presentation" cellspacing="0" cellpadding="0" border="0" style="margin: auto;" class="w100pc">
                                              <tr>
                                                <td class="button-td button-td-primary" style="-moz-border-radius: 8px; -webkit-border-radius: 8px; border-radius: 8px; background: #1dcece; padding: 8px 14px">

                                                    <table align="center" role="presentation" cellspacing="0" cellpadding="0" border="0" class="w100pc">
                                                      <tr>
                                                        <td width="20" style="width: 20px;">&nbsp;</td>
                                                        <td style="font-family: sans-serif; font-size: 15px; line-height: 15px; text-decoration: none;min-width: 100px; font-weight: bold; color: #32466e;" class="text-center button-td-primary w100pc fw">
                                                                             <a class="button-a button-a-primary" href="##PARAM_CUST_ACC_URL##/wallet/ng/transaction-history" target="_blank" style="background: #1dcece; border: 1px solid #1dcece; font-family: sans-serif; font-size: 15px; line-height: 15px; text-decoration: none; color: #32466e; display: block; border-radius: 8px;"><strong style="color: #32466e;font-weight: bold;" class="button-a-copy">View Transactions</strong></a>
                                                        </td>
                                                        <td width="20" style="width: 20px;">&nbsp;</td>
                                                        <td width="20" align="right" style="text-align: right;"><img src="https://www.skrill.com/fileadmin/content/Emails_2015/STRONGVIEW/Images/ARROW_TRAN.png" width="20" height="24" style="display: block;" /></td>
                                                      </tr>
                                                    </table>

                                                </td>
                                              </tr>
                                            </table>
                                            <!---CTA end--->
                                          </td>
                                          <td>
                                            <img alt="spacer" src="https://www.skrill.com/fileadmin/content/Emails_2015/Modular_Templates/spacer.gif" width="1" height="20" style="display: block;" class="w5">
                                          </td>
                                        </tr>
                                      </table>
                                      <!---CTA TABLE end--->
                                    </td>
                                  </tr>
                                  <tr>
                                    <td width="1" height="20" style="height: 20px;" >&nbsp;</td>
                                  </tr>
                                </table>
                              </td>
                              <td width="100" style="font-size:1px; line-height:1px;width: 100px;" class="w30 w30a">&nbsp;</td>
                            </tr>
                          </table>
                        </div>
                        <!--[if gte mso 9]>
                      </v:textbox>
                    </v:rect>
                    <![endif]-->
                  </td>
                </tr>
           
           <!---- NFY_SM_REGISTERED 1914 ----->
           <!---- ##PARAM_CUST_ACC_URL##/wallet/ng/transaction-history ----->
           <!---- Hi  ----->
<!----Table Module ---->
            <tr>
              <td>
                <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="width: margin: auto;" bgcolor="#ffffff">
                  <tr>
                    <td align="center" style="padding: 0px 30px;" class="table-padding">
                      <table cellpadding="0" cellspacing="0" border="0" width="580" style="width: 580px;" class="w100pc stack-items stack-column-center">
                        <tr>
                          <td height="10">&nbsp;</td>
                        </tr>
                        <tr>
                          <td align="left" style="font-family:Arial, Helvetica, sans-serif; font-size:14px; line-height:20px; color:#555555; text-align:left;">
                            <!----Table ---->
                            <table cellpadding="10" cellspacing="0" width="580" style="width:580px; text-align: left;" class="stack-column-center w100pc main_table_2" border="0" >
                              <!----Row 1----->
                              <tr>
                                <th id="Value-col" align="center" style="color: #910590;font-weight: normal;width:250px;border-bottom: solid 2px #910590; text-align: left;" class="stack-items">
                                  Money sent to:
                                </th>
                                <th align="center" class="stack-items" style="color: #910590; font-weight: bold;border-bottom: solid 2px #910590; text-align: left;">
                                  ##RECIPIENT_NAME##
                                </th>
                              </tr>
                              <!----Row 1 end----->
                              <!----Row 2----->
                              <tr>
                                <th id="Value-col" valign="top" align="center" style="color: #910590;font-weight: normal;border-bottom: solid 2px #910590; text-align: left;" class="stack-items">
                                  Your message:
                                </th>
                                <th align="center"  class="stack-items" style="color: #910590; font-weight: bold;border-bottom: solid 2px #910590; text-align: left;">
                                  ##SDR_MESSAGE##
                                </th>
                              </tr>
                              <!----Row 2 end----->
                              <!----Row 3----->
                              <tr>
                                <th id="Value-col" align="center" style="color: #910590;font-weight: normal;border-bottom: solid 2px #910590; text-align: left;" class="stack-items">
                                  Date and time:
                                </th>
                                <th align="center" class="stack-items" style="color: #910590; font-weight: bold;border-bottom: solid 2px #910590; text-align: left;">
                                  ##TIME##
                                </th>
                              </tr>
                              <!----Row 3 end----->
                              <!----Row 4----->
                              <tr>
                                <th id="Value-col" align="center" style="color: #910590;font-weight: normal;border-bottom: solid 2px #910590; text-align: left;" class="stack-items">
                                  Transaction ID:
                                </th>
                                <th align="center"  class="stack-items" style="color: #910590; font-weight: bold;border-bottom: solid 2px #910590; text-align: left;">
                                  ##TRANSACTION_ID##
                                </th>
                              </tr>
                              <!----Row 4 end----->
                            </table>
                            <!----Table ---->
                          </td>
                        </tr>
                        <tr>
                          <td height="10">&nbsp;</td>
                        </tr>
                      </table>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            <!----Table Module end--->

<!-- Body Copy Module -->
            <tr>
              <td style="background-color: #ffffff;">
                <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                  <tr>
                    <td style="padding: 20px 30px; font-family: Airal, sans-serif; font-size: 15px; line-height: 20px; color: #910590;">
                      If you didn’t do this, or do not recognise any of the above details, please contact us right away.
                    </td>
                  </tr>
                  <tr>
                    <td style="padding: 0px 30px 20px; font-family: Airal, sans-serif; font-size: 15px; line-height: 20px; color: #910590; display:##SM_RULE_FRN_TRN_ID_DISPLAY_PROPERTY##;">
                      If your payment is processed but the merchant hasn’t yet credited it to your balance/account, please contact them directly with this reference number: ##FRN_TRN_ID##
                    </td>
                  </tr>
                </table>
              </td>
            </tr>

           <!-- Body Copy Module End -->

 <!-- Sign off -->
            <tr>
              <td style="background-color: #ffffff;">
                <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                  <tr>
                    <td style="padding: 20px 30px; font-family: Airal, sans-serif; font-size: 15px; line-height: 20px; color: #910590;">
                      <strong>Thank you for choosing Skrill</strong>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            <!-- Sign Off END -->
<!-- Skrill Logo Sign Off: BEGIN -->
                <tr>
                  <td style="background-color: #ffffff;">
                    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                      <tr>
                        <td align="left" style="padding: 20px 30px; font-family: Airal, sans-serif; color: #555555;">
                                  <img src="https://www.skrill.com/fileadmin/content/Emails_2015/STRONGVIEW/Images/SKRILL_LOGO_SIGNOFF.png" width="80" height="26" alt="Skrill" border="0" style="display: block;">

                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
                <!-- Skrill Logo Sign Off: END -->
##SM_RULE_BRAND_TRN_HISTORY##
<!-- Footer Nav Module  -->
                <tr>
                  <td style="background-color: #544c63;"  class="h oa">
                    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                      <tr>
                        <!-- Column : BEGIN -->
                        <th valign="middle" align="center" class="stack-items oa show-fallback stack-column-center" >
                          <table role="presentation" cellspacing="0" cellpadding="0" border="0" class="w100pc" width="100%">
                            <tr>
                              <td align="left">
                                <img alt="Box-D" src="https://www.skrill.com/fileadmin/content/Emails_2015/STRONGVIEW/Images/PoweredByPaysafe.png" width="210" height="70" border="0">
                              </td>
                            </tr>
                          </table>
                        </th>
                        <!-- Column : END -->
                        <!-- Column : BEGIN -->
                        <th valign="middle" align="center" class="stack-items oa footer-bg-change show-fallback stack-column-center">
                          <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                            <tr>
                              <th class="h gmailfix-h stack-column-center" height="20" width="60" style="width: 60px;">&nbsp;</th>
                              <th class="stack-items oa stack-column-center">
                                <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                                  <tr>
                                                <th style="font-family: Arial, Helvetica, sans-serif; font-size: 12px; line-height: 18px; color: #ffffff; text-align:center; letter-spacing: 1px;" class="stack-items insert-div oa insert-div show-fallback stack-column-center"><a href="https://www.paysafe.com/en/our-story/" target="_blank" style="font-family:Arial;font-size:12px;line-height:18px;color:#ffffff;text-decoration:none;">About</a></th>
                                    <th class="stack-items oa show-fallback stack-column-center" height="8" width="20" style="display: block;width: 20px;">&nbsp;</th>
                                                <th style="font-family: Arial, Helvetica, sans-serif; font-size: 12px; line-height: 18px; color: #ffffff; text-align:center; letter-spacing: 1px;" class="stack-items oa insert-div show-fallback stack-column-center"><a href="https://www.SKRILL.com/contact-us/?utm_source=strongview&utm_medium=email&utm_campaign=1914" target="_blank" style="font-family:Arial;font-size:12px;line-height:18px;color:#ffffff;text-decoration:none;">Support</a></th>
                                    <th class="stack-items oa show-fallback stack-column-center" height="8" width="20" style="display: block;width: 20px;">&nbsp;</th>
                                                <th style="font-family: Arial, Helvetica, sans-serif; font-size: 12px; line-height: 18px; color: #ffffff; text-align:center; letter-spacing: 1px;" class="stack-items oa insert-div show-fallback stack-column-center"><a href="https://www.SKRILL.com/security-faq/?utm_source=strongview&utm_medium=email&utm_campaign=1914" target="_blank" style="font-family:Arial;font-size:12px;line-height:18px;color:#ffffff;text-decoration:none;">Security</a></th>
                                    <th class="stack-items oa show-fallback stack-column-center" height="8" width="20" style="display: block;width: 20px; ">&nbsp;</th>
                                                <th style="font-family: Arial, Helvetica, sans-serif; font-size: 12px; line-height: 18px; color: #ffffff; text-align:center; letter-spacing: 1px;" class="stack-items oa insert-div show-fallback stack-column-center"><a href="https://www.SKRILL.com/privacy/?utm_source=strongview&utm_medium=email&utm_campaign=1914" target="_blank" style="font-family:Arial;font-size:12px;line-height:18px;color:#ffffff;text-decoration:none;">Privacy</a></th>
                                    <th class="stack-items oa show-fallback stack-column-center" height="8" width="20" style="display: block;width: 20px;">&nbsp;</th>
                                                <th style="font-family: Arial, Helvetica, sans-serif; font-size: 12px; line-height: 18px; color: #ffffff; text-align:center; letter-spacing: 1px;" class="stack-items oa show-fallback stack-column-center"><a href="https://www.SKRILL.com/termsofuse/?utm_source=strongview&utm_medium=email&utm_campaign=1914" target="_blank" style="font-family:Arial;font-size:12px;line-height:18px;color:#ffffff;text-decoration:none;">Terms</a></th>
                                  </tr>
                                </table>
                              </th>
                              <th class="h gmailfix-h stack-column-center" height="20" width="20" style="width: 20px;">&nbsp;</th>
                            </tr>
                          </table>
                        </th>
                        <!-- Column : END -->
                      </tr>
                    </table>
                  </td>
                </tr>
                <!-- Footer Nav Module End -->
<!-- Footer Burger Menu Module -->
                <tr>
                  <td>
                    <table width="640" height="58" class="w100pc autoh wr gmailfix-h oa-hide" cellpadding="0" cellspacing="0" border="0" bgcolor="#544c63" style="width: 640px;height: 1px;display: none;">
                      <tr>
                        <td bgcolor="#544c63" valign="top" class="wr w100pc autoh" width="1" height="1" style="width:1px; height: 1px;">
                          <!---mobile reveal---->
                          <!--[if !mso]><!-->
                          <div style="display:none; font-size:0; line-height:0; max-height:0; mso-hide:all !important; visibility:hidden; overflow:hidden;" class="mob-reveal">
                            <form style="border-style: none;border-width: 0px;" class="formbg">
                              <div id="wrapper" style="background-color: #544c63;" >
                                <table border="0" cellpadding="0" cellspacing="0" style="border-collapse: collapse; border-spacing: 0; table-layout: fixed; ; border-bottom-color: #cccccc; border-bottom: 1px solid #cccccc" width="100%" class="formbg">
                                  <tr>
                                    <td>
                                      <!--[if mso]>
                                      <p style="display: none;">
                                        <![endif]-->
                                        <input id="mobile-checkbox1" style="display: none!important; max-height: 0; visibility: hidden;" type="checkbox">
                                        <!--[if mso]>
                                      </p>
                                      <![endif]-->
                                      <table align="center" border="0" cellpadding="0" cellspacing="0" class="container formbg" style="border-collapse: collapse; border-spacing: 0; margin: auto; min-width: 600px;" width="600" >
                                        <tr>
                                          <td></td>
                                          <td >
                                            <a href="https://www.skrill.com/$lowercase(lookup(LANG_LOCALE))$" target="_blank"><img src="https://www.skrill.com/fileadmin/content/Emails_2015/STRONGVIEW/Images/PoweredByPaysafe.png" style="width:210px; height:70px;display: block !important; float: left;"></a>
                                            <label for="mobile-checkbox1" id="mobile-label-footer" style="display: none;" class="formbg">
                                            <b></b>
                                            <b></b>
                                            <b></b>
                                            </label>
                                            <!--[if mso]>
                                          </td>
                                          <td>
                                            <![endif]-->
                                            <table width="100%" align="center" border="0" cellpadding="0" cellspacing="0" class="menu formbg">
                                              <tr>
                                                <td style="padding-left: 80px;" class="pdl0">
                                                  <div id="menu-wrapper-footer">
                                                    <!--[if mso]>
                                                    <table border="0" cellpadding="0" cellspacing="0">
                                                      <tr>
                                                        <td>
                                                          <![endif]-->
                                                          <table align="left" border="0" cellpadding="10" cellspacing="0" class="menu" style="border-collapse: collapse; border-spacing: 0;">
                                                            <tr>
                                                              <td nowrap style="font-family: Arial, sans-serif; font-size: 13px; line-height: 1; text-transform: uppercase;letter-spacing: 2px;">
                                                                <a href="https://www.paysafe.com/en/our-story/" target="_blank" class="menu-item" style="color: #575452; line-height: 1; text-decoration: none;">About</a>
                                                              </td>
                                                            </tr>
                                                          </table>
                                                          <!--[if mso]>
                                                        </td>
                                                        <td>
                                                          <![endif]-->
                                                          <table align="left" border="0" cellpadding="10" cellspacing="0" class="menu" style="border-collapse: collapse; border-spacing: 0;">
                                                            <tr>
                                                              <td nowrap style="font-family: Arial, sans-serif; font-size: 13px; line-height: 1; text-transform: uppercase;letter-spacing: 2px;">
                                                                <a href="https://www.SKRILL.com/contact-us/?utm_source=strongview&utm_medium=email&utm_campaign=1914" target="_blank" class="menu-item" style="color: #575452; line-height: 1; text-decoration: none;">Support</a>
                                                              </td>
                                                            </tr>
                                                          </table>
                                                          <!--[if mso]>
                                                        </td>
                                                        <td>
                                                          <![endif]-->
                                                          <table align="left" border="0" cellpadding="10" cellspacing="0" class="menu" style="border-collapse: collapse; border-spacing: 0;">
                                                            <tr>
                                                              <td nowrap style="font-family: Arial, sans-serif; font-size: 13px; line-height: 1; text-transform: uppercase;letter-spacing: 2px;">
                                                                <a href="https://www.SKRILL.com/security-faq/?utm_source=strongview&utm_medium=email&utm_campaign=1914" target="_blank" class="menu-item" style="color: #575452; line-height: 1; text-decoration: none;">Security</a>
                                                              </td>
                                                            </tr>
                                                          </table>
                                                          <!--[if mso]>
                                                        </td>
                                                        <td>
                                                          <![endif]-->
                                                          <table align="left" border="0" cellpadding="10" cellspacing="0" class="menu" style="border-collapse: collapse; border-spacing: 0;">
                                                            <tr>
                                                              <td nowrap style="font-family: Arial, sans-serif; font-size: 13px; line-height: 1; text-transform: uppercase;letter-spacing: 2px;">
                                                                <a href="https://www.SKRILL.com/privacy/?utm_source=strongview&utm_medium=email&utm_campaign=1914" target="_blank" class="menu-item" style="color: #575452; line-height: 1; text-decoration: none;">Privacy</a>
                                                              </td>
                                                            </tr>
                                                          </table>
                                                          <!--[if mso]>
                                                        </td>
                                                        <![endif]-->
                                                        <table align="left" border="0" cellpadding="10" cellspacing="0" class="menu" style="border-collapse: collapse; border-spacing: 0;">
                                                          <tr>
                                                            <td nowrap style="font-family: Arial, sans-serif; font-size: 13px; line-height: 1; text-transform: uppercase;letter-spacing: 2px;">
                                                              <a href="https://www.SKRILL.com/termsofuse/?utm_source=strongview&utm_medium=email&utm_campaign=1914" target="_blank" class="menu-item" style="color: #575452; line-height: 1; text-decoration: none;">Terms</a>
                                                            </td>
                                                          </tr>
                                                        </table>
                                                        <!--[if mso]>
                                                        </td>
                                                      </tr>
                                                    </table>
                                                    <![endif]-->
                                                  </div>
                                                </td>
                                              </tr>
                                            </table>
                                          </td>
                                        </tr>
                                      </table>
                                    </td>
                                  </tr>
                                </table>
                              </div>
                            </form>
                          </div>
                          <!--<![endif]-->
                          <!---mobile reveal end---->
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
                <!---footer burger end--->
<!-- Email Footer : BEGIN -->
                     <tr>
                  <td>
                          <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="width: margin: auto;" bgcolor="#ffffff">
                <tr>
                  <td style="padding: 20px 30px; font-family: Arial,sans-serif; font-size: 9px; line-height: 15px; text-align: left; color: #666666;">
                    Copyright © 2026 Skrill Limited. Skrill  is a registered trademark of Skrill  Ltd. All rights reserved.<br/><br/>

                        Skrill Limited is registered in England and Wales with company number 04260907 and its registered office is at 2 Gresham Street, London EC2V 7AD. Authorised and regulated by the Financial Conduct Authority under the Electronic Money Regulations 2011 (FRN: 900001) for the issuance of electronic money.<br/><br/>
                        We use cookies and similar technology in some of our emails which contain hyperlinks, each of which has a unique tag. They help us to understand a little bit about how you interact with our emails, and are used to improve our future email communications to you. If you click on links contained in this email it will allow us to track your use of our website. For more information about our use of cookies and similar technology please see our <a href="https://www.paysafe.com/paysafegroup/cookie-policy/"  target="_blank" style="color:#910590; text-decoration:underline" >Cookies Notice</a>.<br/><br/>

                          In accordance with relevant Data Protection and Privacy laws, Paysafe is committed to protecting your privacy. If you wish to know more, please access our <a href="https://www.SKRILL.com/privacy/?utm_source=strongview&utm_medium=email&utm_campaign=1914" target="_blank" style="color:#910590; text-decoration:underline">Privacy Policy</a>.<br /><br/>

                      To ensure that Skrill emails reach your inbox, please add <a href="mailto:no-reply@email.SKRILL.com" style="text-decoration:none; font-family: Arial,sans-serif; font-size: 9px; line-height: 15px; text-align: left; color: #666666;"><strong>no-reply@email.SKRILL.com</strong></a> to your email safe list. <br/><br/>

                  </td>
                </tr>
              </table>
                         </td>
                </tr>
                     <!-- Email Footer : End -->

<tr><td><span style="font-size: 6px; color: #ebeff0;margin: auto;">NFY_SM_REGISTERED 1914</span></td></tr>

</table>
              <!-- Email Body : END -->



              <!--[if mso | IE]>
            </td>
          </tr>
        </table>
        <![endif]-->
      </center>
    </body>
    </html>
"""


def test_nfy_password_created_template():
    """T-001: classic table-layout template preserves body and strips footer/noise."""
    result = extract_plain_text(NFY_PASSWORD_CREATED_HTML)

    assert "You have successfully created a password for your Skrill account." in result
    assert "If you did not authorise this change, please contact the" in result
    assert "Skrill Help Team" in result
    assert "Best Regards," in result
    assert "Skrill" in result

    assert "Copyright" not in result
    assert "registered in England and Wales" not in result
    assert "We use cookies" not in result
    assert "NFY_PASSWORD_CREATED" not in result

    assert "#f4f4f4" not in result
    assert "#910590" not in result


def test_nfy_sm_registered_template():
    """T-002: modern modular template preserves body and strips footer/MSO/noise."""
    result = extract_plain_text(NFY_SM_REGISTERED_HTML)

    assert "YOU JUST SENT" in result
    assert "If you didn\u2019t do this, or do not recognise any of the above details" in result
    assert "please contact us right away" in result
    assert "If your payment is processed but the merchant hasn\u2019t yet credited it" in result
    assert "Thank you for choosing Skrill" in result

    assert "About" not in result
    assert "Support" not in result
    assert "Privacy" not in result

    assert "Copyright" not in result
    assert "NFY_SM_REGISTERED" not in result

    assert "#592357" not in result

    assert "font-family: sans-serif" not in result
    assert "PixelsPerInch" not in result
