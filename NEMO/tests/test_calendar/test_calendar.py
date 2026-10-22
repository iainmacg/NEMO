from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from NEMO.models import Reservation, Tool, UsageEvent, User
from NEMO.tests.test_utilities import NEMOTestCaseMixin, create_user_and_project
from NEMO.views.customization import ApplicationCustomization, CalendarCustomization


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
        account_manager, account_manager_project = create_user_and_project()
        pi.managed_projects.add(team_project)
        account_manager.managed_accounts.add(team_project.account)
        # other user is also a member of the team project, but not a PI
        other_user.projects.add(team_project)
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
            UsageEvent.objects.create(
                tool=tool, user=user, operator=user, project=project, start=start, end=start + timedelta(hours=1)
            )
        feed_data = {
            "start": (start - timedelta(days=1)).strftime("%Y-%m-%d"),
            "end": (start + timedelta(days=1)).strftime("%Y-%m-%d"),
            "team_schedule": "true",
        }
        reservation_feed = {**feed_data, "event_type": "reservations"}
        usage_feed = {**feed_data, "event_type": f"{ApplicationCustomization.get('facility_name').lower()} use"}
        # PI and account manager see team schedule option and only reservations and usage on projects they manage
        for manager in [pi, account_manager]:
            self.login_as(manager)
            response = self.client.get(reverse("calendar"))
            self.assertContains(response, 'id="extra-links-team-schedule"')
            self.assertTrue(response.context["team_schedule_usage"])
            for feed in [reservation_feed, usage_feed]:
                response = self.client.get(reverse("event_feed"), feed)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, team_member.username)
                self.assertNotContains(response, other_user.username)
        # Project member doesn't see the option or any events by default
        self.login_as(other_user)
        self.assertNotContains(self.client.get(reverse("calendar")), 'id="extra-links-team-schedule"')
        for feed in [reservation_feed, usage_feed]:
            response = self.client.get(reverse("event_feed"), feed)
            self.assertNotContains(response, team_member.username)
            self.assertNotContains(response, other_user.username)
        # Unless the team schedule is enabled for project members, which only applies to reservations
        CalendarCustomization.set("calendar_team_schedule_project_members", "enabled")
        response = self.client.get(reverse("calendar"))
        self.assertContains(response, 'id="extra-links-team-schedule"')
        self.assertFalse(response.context["team_schedule_usage"])
        response = self.client.get(reverse("event_feed"), reservation_feed)
        self.assertContains(response, team_member.username)
        self.assertContains(response, other_user.username)
        response = self.client.get(reverse("event_feed"), usage_feed)
        self.assertNotContains(response, team_member.username)
        self.assertNotContains(response, other_user.username)
