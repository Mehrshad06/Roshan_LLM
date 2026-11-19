from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render


def signup(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = UserCreationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST":
        # SQLite's IMMEDIATE transaction serializes the form's duplicate-name
        # check and the insert, including two simultaneous registrations.
        try:
            with transaction.atomic():
                if form.is_valid():
                    user = form.save()
                    login(request, user)
                    return redirect("dashboard")
        except IntegrityError:
            form.add_error("username", "این نام کاربری قبلاً ثبت شده است.")
    return render(request, "registration/signup.html", {"form": form})
