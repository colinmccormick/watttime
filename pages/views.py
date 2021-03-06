from django.shortcuts import render, render_to_response
from django.http import HttpResponse, HttpResponseRedirect
from models import ContactForm
from django.template import RequestContext
from django import forms
from django.forms.widgets import *
from django.core.mail import send_mail, BadHeaderError
from django.core.urlresolvers import reverse
from windfriendly.models import NE, BPA, CAISO, MARGINAL_FUELS
from windfriendly.parsers import NEParser, BPAParser, CAISOParser
from settings import EMAIL_HOST_USER

def signed_up(request):
    return render(request, 'pages/signed_up.html')

def faq(request):
#    return render(request, 'pages/placeholder.html', {'title': 'FAQ'})
    return render(request, 'pages/faq.html')

def about_us(request):
 #   return render(request, 'pages/placeholder.html', {'title': 'About WattTime'})
    return render(request, 'pages/about_us.html')

def how_it_works(request):
#    return render(request, 'pages/placeholder.html', {'title': 'How WattTime works'})
    return render(request, 'pages/how_it_works.html')

def terms_of_service(request):
#    return render(request, 'pages/placeholder.html', {'title': 'Terms of Service'})
    return render(request, 'pages/terms_of_service.html')

def BPA_status(request):
#    return render(request, 'pages/placeholder.html', {'title': 'New England current status'})
    # get current data
    if BPA.objects.count() == 0:
        parser = BPAParser()
        parser.update()
    datum = BPA.latest_point()
    print BPA.latest_point(), BPA.latest_date()
    percent_green = datum.fraction_green() * 100.0
    marginal_fuel = MARGINAL_FUELS[datum.marginal_fuel]

     # compose message
    greenery = str(int(percent_green + 0.5))
    if percent_green < 7:
        message = "Right now in the Pacific Northwest only {p} percent of all electricity is coming from clean wind power. This is below average. It's a really good time to save energy in the Northwest!"
    elif percent_green < 18:
        message = "Right now in the Pacific Northwest {p} percent of all electricity is coming from clean wind power. This is about average for this time of year."
    else:
        message = "Right now in the Pacific Northwest {p} percent of all electricity is coming from clean wind power. This is cleaner than average. Not a bad time to use energy!"
    message = message.format(p = greenery, fuel = marginal_fuel.lower())
    return render(request, 'pages/BPA_status.html', {'marginal_message' : message})

def CA_status(request):
#    return render(request, 'pages/placeholder.html', {'title': 'New England current status'})
    # get current data
    if CAISO.objects.count() == 0:
        parser = CAISOParser()
        parser.update()
    datum = CAISO.latest_point()
    print CAISO.latest_point(), CAISO.latest_date()
    percent_green = datum.fraction_green() * 100.0
    marginal_fuel = MARGINAL_FUELS[datum.marginal_fuel]

     # compose message
    greenery = str(int(percent_green + 0.5))
    if percent_green < 6.5:
        message = "Right now Californian electricity is DIRTIER than average for this time of year. Only {p} percent of electricity is coming from 'Eligible Intermittent Resources' - renewable energy. You can help us do better! This is a great time to save energy."
    elif percent_green < 9.5:
        message = "Right now California renewable energy is at about AVERAGE cleanliness, with {p} percent of all power coming from 'Eligible Intermittent Resources' - renewable energy. "
    else:
        message = "Right now California is CLEANER than average, with {p} percent of all power coming from 'Eligible Intermittent Resources' - renewable energy.  Not a bad time to use energy!"
    message = message.format(p = greenery, fuel = marginal_fuel.lower())
    return render(request, 'pages/CA_status.html', {'marginal_message' : message})

def NE_status(request):
#    return render(request, 'pages/placeholder.html', {'title': 'New England current status'})
    # get current data
    if NE.objects.count() == 0:
        parser = NEParser()
        parser.update()
    datum = NE.latest_point()
    print NE.latest_point(), NE.latest_date()
    percent_green = datum.fraction_green() * 100.0
    marginal_fuel = MARGINAL_FUELS[datum.marginal_fuel]

     # compose message
    greenery = str(int(percent_green + 0.5))
    if marginal_fuel in ['Coal', 'Oil']:
        message = "Right now in New England {p} percent of power is coming from renewable energy. You can change this number! Right now any power that's reduced will disproportionately affect {fuel}. That means this is a great time to SAVE energy."
    elif marginal_fuel in ['Natural Gas', 'Refuse', 'Mixed']:
        message = "Right now in New England {p} percent of power is coming from renewable energy. Right now any additional power that's needed will come from {fuel}. That means this is an AVERAGE time to use energy."
    elif marginal_fuel in ['Wood', 'Wind', 'Water']:
        message = "Right now in New England {p} percent of power is coming from renewable energy. Right now any additional power that's needed will come from {fuel}. That means this is actually a pretty GOOD time to use electricity."
    else:
        message = "Right now in New England {p} percent of power is coming from renewable energy."
    message = message.format(p = greenery, fuel = marginal_fuel.lower())
    return render(request, 'pages/NE_status.html', {'marginal_message' : message})


def status_offline(request):
    return render(request, 'pages/status.html', {'marginal_message' : 'Status is offline until July 1.'})

def status(request):

        return render(request, 'pages/status.html', {'marginal_message' : message})
    
def contact(request):
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data

            if cd['subject'] and cd['message'] and cd['email']:
                try:
                    send_mail(
                        cd['subject'],
            cd['email'] + '\n' + cd['message'],
            cd['email'],
            [EMAIL_HOST_USER],
            fail_silently=False,
                        )
                    url = reverse('contact_thank_you')
                    return HttpResponseRedirect(url)
                except BadHeaderError:
                    return HttpResponse('Invalid header found.')
            else:
                return HttpResponse('Make sure all fields are entered.')
    else:
        form = ContactForm()

    return render_to_response('pages/contact.html', {'form':form}, RequestContext(request))

def thankyou(request):
    return render_to_response('pages/contact_thank_you.html')
    
def facebook_pilot(request):
    return render(request, 'pages/facebook_pilot.html')
    
def sierra_pilot(request):
    return render(request, 'pages/sierra_pilot.html')
