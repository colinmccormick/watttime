from django.db import models
#from django.contrib.auth.models import User
from django.forms import ModelForm, CheckboxSelectMultiple, RadioSelect
from django_localflavor_us.models import PhoneNumberField, USStateField
from django_localflavor_us.us_states import STATE_CHOICES

class User(models.Model):
    # name
    name = models.CharField(max_length=100)

    # email
    email = models.EmailField()

    # US phone
    phone = PhoneNumberField()

    # US state
    state = USStateField(default='MA')


    # state logic
    VALID_STATE_CHOICES = ('MA',)

    def is_valid_state(self):
        if self.state in self.VALID_STATE_CHOICES:
            return True
        else:
            return False

    def long_state_name(self):
        try:
            return dict(STATE_CHOICES)[self.state]
        except KeyError:
            return self.state



class UserProfile(models.Model):

    userid = models.ForeignKey(User)

    # air conditioning
    AC_CHOICES = (
        (0, 'None'),
        (1, 'Central A/C'),
        (2, 'Window unit'),
        (3, 'Other'),
        )
    ac = models.IntegerField('Air conditioner type',
                             blank=False, default=0,
                             choices=AC_CHOICES,
                             )

    # furnace and water heater
    HEATER_CHOICES = (
        (0, 'None'),
        (1, 'Electric'),
        (2, 'Gas'),
        (3, 'Other'),
        )
    furnace = models.IntegerField('Furnace type',
                                  blank=False, default=0,
                                  choices=HEATER_CHOICES,
                                  )
    water_heater = models.IntegerField('Water heater type',
                                       blank=False, default=0,
                                       choices=HEATER_CHOICES,
                                       )

    # when to text
    SENDTEXT_HOURS_CHOICES = (
        (0, 'Bright and early (6am-9am)'),
        (1, 'Morning  (9am-noon)'),
        (2, 'Afternoon (noon-3pm)'),
        (3, 'After school (3pm-6pm)'),
        (4, 'Evening (6pm-9pm)'),
        (5, 'Night (9pm-midnight)'),
        )
 #   weekday_sendtext_hours = models.IntegerField('When you can receive texts on weekdays',
  #                                               blank=True,
  #                                               choices=SENDTEXT_HOURS_CHOICES,
#)
   # weekend_sendtext_hours = models.IntegerField('When you can receive texts on weekends',
   #                                             # blank=False, default=0,
   #                                              choices=SENDTEXT_HOURS_CHOICES,
    #)

    # how often to contact
    SENDTEXT_FREQ_CHOICES = (
        (1, 'About once an hour! Woo!'),
        (2, 'About once a day'),
        (3, 'About once a week'),
        )
    text_freq = models.IntegerField('How often you want to receive texts',
                                    blank=False, default=1,
                                    choices=SENDTEXT_FREQ_CHOICES,
                                    )

    # goals for using service
    GOALS_CHOICES = (
        (0, "I'm up for anything"),
        (1, 'Boycott coal'),
        (2, 'Maximize wind'),
        (3, 'Minimize carbon'),
        )
    goal = models.IntegerField('Which goals would you like to receive notifications about?',
                               blank=False, default=0,
                              # blank=True,
                               choices=GOALS_CHOICES,
                               )


class SplashForm(ModelForm):
    class Meta:
        model = User
        fields = ('email',)


class NewUserForm(ModelForm):
    class Meta:
        model = User
    #    fields = '__all__'


class UserProfileForm(ModelForm):
    class Meta:
        model = UserProfile
        exclude = ['userid']
        widgets = {
            'goal': RadioSelect(),
            'ac': RadioSelect(),
            'furnace': RadioSelect(),
            'water_heater': RadioSelect(),
            'text_freq': RadioSelect(),
          #  'weekend_sendtext_hours': CheckboxSelectMultiple(),
          #  'weekday_sendtext_hours': CheckboxSelectMultiple(),
            }