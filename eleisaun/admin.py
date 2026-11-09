from django.contrib import admin

from .models import (AuditLog, Centre, Contestant, Election, Evidence, Municipality, Party, Postu, Profile,
                     Report, ResultLine, Suku)


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Municipality)
class MunicipalityAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_special")


@admin.register(Postu)
class PostuAdmin(admin.ModelAdmin):
    list_display = ("name", "municipality")
    list_filter = ("municipality",)
    search_fields = ("name",)


@admin.register(Suku)
class SukuAdmin(admin.ModelAdmin):
    list_display = ("name", "postu")
    list_filter = ("postu__municipality",)
    search_fields = ("name",)


@admin.register(Centre)
class CentreAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "suku", "registered_voters")
    list_filter = ("suku__postu__municipality",)
    search_fields = ("code", "name")


class ContestantInline(admin.TabularInline):
    model = Contestant
    extra = 0


@admin.register(Election)
class ElectionAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "round", "date", "is_active")
    inlines = [ContestantInline]


@admin.register(Party)
class PartyAdmin(admin.ModelAdmin):
    list_display = ("acronym", "name", "color")


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "organization", "party")
    list_filter = ("role",)
    filter_horizontal = ("centres",)
    autocomplete_fields = ()
    raw_id_fields = ("user",)


class LineInline(admin.TabularInline):
    model = ResultLine
    extra = 0
    can_delete = False
    readonly_fields = ("contestant", "votes")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Report)
class ReportAdmin(ReadOnlyAdmin):
    list_display = ("centre", "submitted_by", "voted", "status", "version", "updated_at")
    list_filter = ("status", "election")
    inlines = [LineInline]


@admin.register(AuditLog)
class AuditAdmin(ReadOnlyAdmin):
    list_display = ("id", "created", "username", "action", "target", "ip")
    list_filter = ("action",)
