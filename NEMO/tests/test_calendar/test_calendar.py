from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from NEMO.models import Reservation, Tool, User
from NEMO.tests.test_utilities import NEMOTestCaseMixin, create_user_and_project


class CalendarTestCase(NEMOTestCaseMixin, TestCase):
    tool = None
    owner = None

    def setUp(self):
        global tool, owner
        owner = User.objects.create(username="mctest", first_name="Testy", last_name="McTester")
        tool = Tool.objects.create(name="test_tool", primary_owner=owner, _category="Imaging")

    def test_calendar_urls(self):
        # if not logged in, it should send an error message
        response = self.client.get(reverse("calendar"), follow=True)
        self.assert_response_is_failed_login(response)

        self.login_as_user()
        response = self.client.get(reverse("calendar"), follow=True)
        self.assertEqual(response.status_code, 200)

        response = self.client.get(reverse("calendar", kwargs={"item_type": "tool", "item_id": tool.id}), follow=True)
        self.assertEqual(response.status_code, 200)

    def test_team_schedule(self):
        team_member, team_project = create_user_and_project()
        other_user, other_project = create_user_and_project()
        pi, pi_project = create_user_and_project()
        pi.managed_projects.add(team_project)
        start = timezone.now().replace(hour=10, minute=0, second=0, microsecond=0)
        for user, project in [(team_member, team_project), (other_user, other_project)]:
            Reservation.objects.create(
                tool=tool,
                start=start,
                end=start + timedelta(hours=1),
                creator=user,
                user=user,
                project=project,
                short_notice=False,
            )
        feed_data = {
            "start": (start - timedelta(days=1)).strftime("%Y-%m-%d"),
            "end": (start + timedelta(days=1)).strftime("%Y-%m-%d"),
            "event_type": "reservations",
            "team_schedule": "true",
        }
        # PI sees team schedule option and only reservations on projects they manage
        self.login_as(pi)
        self.assertContains(self.client.get(reverse("calendar")), 'id="extra-links-team-schedule"')
        response = self.client.get(reverse("event_feed"), feed_data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, team_member.username)
        self.assertNotContains(response, other_user.username)
        # Regular user doesn't see the option or any reservations
        self.login_as(other_user)
        self.assertNotContains(self.client.get(reverse("calendar")), 'id="extra-links-team-schedule"')
        response = self.client.get(reverse("event_feed"), feed_data)
        self.assertNotContains(response, team_member.username)
        self.assertNotContains(response, other_user.username)
