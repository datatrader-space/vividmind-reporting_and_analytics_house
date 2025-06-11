from django.db import models
from django.contrib.auth import get_user_model
#from tagging.fields import TagField
#from tagging.mixins import TaggedModelMixin
from django.contrib.auth import get_user_model


User = get_user_model()

class Customer( models.Model):
    """
    # FIXME Backward compatibility with Darrxscale
    # ?? Not needed in this panel

    Args:
        TaggedModelMixin ([type]): [description]
        models ([type]): [description]

    Returns:
        [type]: [description]
    """
    user = models.OneToOneField(User,
                                on_delete=models.CASCADE,
                                primary_key=True
                                )

    stripe_customer_id = models.CharField(
        max_length=200,
        null=True,
        blank=True
    )

    stripe_subscription_id = models.CharField(
        max_length=200,
        null=True,
        blank=True
    )

    subscription_item_id = models.CharField(
        max_length=200,
        null=True,
        blank=True
    )

    email_address = models.EmailField(null=True)
    name = models.CharField(blank=True,
                            null=True,
                            max_length=50
                            )

    #tags = TagField()

    def __str__(self):
        return (self.user.username)
