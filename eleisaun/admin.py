from django.contrib import admin

from .models import (Aldeia, AdministrativePost, AuditLog, Centre, Contestant, Election, Evidence, Municipality,
                     Nasaun, Party, Profile, Report, ResultLine, TOTPDevice, Village)


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Municipality)
class MunicipalityAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "hckey")


@admin.register(AdministrativePost)
class PostAdmin(admin.ModelAdmin):
    list_display = ("name", "municipality")
    list_filter = ("municipality",)
    search_fields = ("name",)


@admin.register(Village)
class VillageAdmin(admin.ModelAdmin):
    list_display = ("name", "administrativepost")
    list_filter = ("administrativepost__municipality",)
    search_fields = ("name",)


@admin.register(Aldeia)
class AldeiaAdmin(admin.ModelAdmin):
    list_display = ("name", "village")
    search_fields = ("name",)


@admin.register(Nasaun)
class NasaunAdmin(admin.ModelAdmin):
    list_display = ("name",)


@admin.register(Centre)
class CentreAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "village", "nasaun", "registered_voters")
    list_filter = ("village__administrativepost__municipality", "nasaun")
    search_fields = ("code", "name")


@admin.register(TOTPDevice)
class TOTPAdmin(admin.ModelAdmin):
    list_display = ("user", "confirmed", "created")
    exclude = ("secret",)
    readonly_fields = ("user", "confirmed", "last_counter", "created")

    def has_add_permission(self, request):
        return False


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
