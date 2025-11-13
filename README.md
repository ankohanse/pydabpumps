[![license](https://img.shields.io/github/license/toreamun/amshan-homeassistant?style=for-the-badge)](LICENSE)
[![buy_me_a_coffee](https://img.shields.io/badge/If%20you%20like%20it-Buy%20me%20a%20coffee-yellow.svg?style=for-the-badge)](https://www.buymeacoffee.com/ankohanse)


# pydabpumps

Python library for retrieving sensor information from DAB Pumps devices.
This component connects to the remote DAB Pumps servers and automatically determines which installations and devices are available there.

The custom component was tested with a ESybox 1.5kw combined with a DConnect Box 2. It has also been reported to function correctly for ESybox Mini and ESybox Diver.

Disclaimer: this library is NOT created by DAB Pumps


# Prerequisites
This library depends on the backend servers for the DAB Pumps H2D app, DAB Live app or DConnect app to retrieve the device information from.

- For most pumps:

  All DAB's new network-capable pumps will progressively be connected with H2D. At the moment, H2D is supported by Esybox Mini3, Esybox Max, NGPanel, NGDrive and the new EsyBox.

  Newer pump devices will have integrated connectivity (Esybox MAX and Esybox Mini), while older pumps might require a DConnect Box/Box2 device (Esybox and Esybox Diver).

  Using free functionalilty you will be able to check the system's basic parameters via the H2D app and this library. To allow to edit settings via the H2D app and this library you will need a Dab Pumps subscription to premium H2D. Follow the steps under [H2D](#h2d)

- For other pumps:

  The older Dab Live and DConnect apps are being replaced by H2D, but are still available.

  Esybox Mini3 pumps are supported on the DAB Live app with a free DAB Live account, or on the DConnect App with a paid account. Follow the steps under either [DAB Live](#dab-live) or [DConnect](#dconnect).

  To see whether your pump device is supported via DConnect, browse to [internetofpumps.com](https://internetofpumps.com/), select 'Professional Users' and scroll down to the operation diagram. A free trial period is available, after that there is a yearly subscription to DAB Pumps DConnect (US$ 20 in 2024). Follow the steps under [DConnect](#dconnect).

## H2D
If you have a pump that is supported by the H2D app then:
- Download the H2D app on your phone or tablet
- Setup an account to use with the app.
- Follow the steps in the app to register your pump.
- Create a separate account for use with this libary; follow the steps under  [Multiple Account Logins](#multiple-account-logins) below.

## DAB Live
If you have a pump that is supported for DAB Live then:
- Download the DAB Live app on your phone or tablet
- Open the app and create a new account. When asked between 'Professional' or 'End User' either are good, this has no implications on the app or the use of this library.
- Follow the steps in the app to register your pump.

## DConnect
If you have a device that is supported for DConnect then:
- Enable your DAB Pumps devices to connect to DConnect. For more information on this, see the manual of your device.
- Install the DConnect app, or open the DConnect website in a browser.
- Setup an account for DConnect
- Add your installation via the device serial number.
- Setup a sepatate account for use with this library; follow the steps under  [Multiple Account Logins](#multiple-account-logins) below.

## Multiple Account Logins
The H2D app and the DConnect app and website seem to have a problem with multiple logins from the same account. I.e. when already logged into the app or website, then a subsequent login via this library may fail. 

Therefore it is recommended to create a separate account within DAB Pumps H2D or DConnect that is specific for script use. 
- Create a fresh email address at gmail, outlook or another provider. 

- For H2D:
  - Login to the H2D app using your regular email address.
  - In the bottom of the H2D app select 'Installations'.
  - At the top of the page the owner is displayed. This is the name associated with your regular email address. Press the '>' next to it.
  - Click on '+ Invite another user'.
  - Fill in the email address you created specific for script use. Select user category 'Professional' to make use of all functionality of this library. Press 'Invite' and then 'Continue'.
  - Follow the steps as described in the invitation email to register the new email address. Note that this is handled via the DConnect website (which is expected to be renamed to H2D soon).

- For DConnect:
  - Open the Dconnect app and logout from your normal account if needed.
  - Press 'Login' and then 'Register'. This will open the DConnect website.
  - Enter the email address you created for script use and choose a password. The choice between 'Professional' or 'End User' either are good as this is only used for marketing purposes;  it has no implications on the website, app or this library.
  - Fill in all other details on the form and press 'Register'.
  - Go back to the DConnect app and login using your normal account.
  - Click on your installation and then at the bottom of the page on 'Installation Sharing'.
  - Click on 'Add an installer' to make use of all functionality of this library.
  - Fill in the email address you created specific for script use and click '+'. 
  
  


# Usage

The library is available from PyPi using:
`pip install pydabpumps`

See example_api_use.py for an example of usage.
