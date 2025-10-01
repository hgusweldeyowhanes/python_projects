from django.shortcuts import render
from rest_framework import serializers,generics,permissions
from rest_framework.response import Response
from banners import models
from django.core.cache import cache
from django.db.models import Q
from banners import serializers
from django.utils import timezone
from rest_framework.exceptions import ValidationError
# Create your views here.

class BannerListView(generics.ListAPIView):
    serializer_class = serializers.FrontPageImageConfigurationSerializer

    def get_permissions(self):
        location = self.request.GET.get("location")
        
        if location and int(location) == models.FrontPageImageConfiguration.ImageLocation.DEPOSIT_BANNER:
            return [permissions.IsAuthenticated()]
        return [permissions.AllowAny()] 
    def get_queryset(self):
        """Return filtered and cached banners"""
        cache_key = self._cache_key()
        if (cached := cache.get(cache_key)) is not None:
            return cached

        queryset = (
            models.FrontPageImageConfiguration.objects.filter(is_active=True)
            .order_by("order")
        )
        queryset = self._apply_filters(queryset)
        queryset = self._apply_time_filters(queryset)

        cache.set(cache_key, queryset, timeout=300)
        return queryset

    def _cache_key(self):
        """Generate unique cache key based on filters"""
        params = {k: self.request.GET.get(k) for k in ["location", "channel", "provider"]}
        return "banners_" + "_".join(f"{k}_{v}" for k, v in params.items())

    def _apply_filters(self, queryset):
        """Validate and apply location, channel, and provider filters"""
        filters = {
            "location": (models.FrontPageImageConfiguration.ImageLocation.choices, "image_location"),
            "channel": (models.FrontPageImageConfiguration.Channel.choices, "image_channel"),
            "provider": (models.FrontPageImageConfiguration.Provider.choices, "provider"),
        }

        for param, (choices, field) in filters.items():
            value = self.request.GET.get(param)
            if not value:
                continue

            try:
                value_int = int(value)
            except (ValueError, TypeError):
                raise ValidationError({param: f"{param.capitalize()} must be an integer"})

            valid_values = [choice[0] for choice in choices]
            if value_int not in valid_values:
                raise ValidationError({param: f"Invalid {param} value"})

            # Include BOTH option if available
            if hasattr(models.FrontPageImageConfiguration, param.capitalize()):
                both = getattr(models.FrontPageImageConfiguration, param.capitalize()).BOTH
                queryset = queryset.filter(Q(**{field: value_int}) | Q(**{field: both}))
            else:
                queryset = queryset.filter(**{field: value_int})

        return queryset

    def _apply_time_filters(self, queryset):
        """Show only currently active banners"""
        now = timezone.now()
        return queryset.filter(
            Q(start_time__lte=now) | Q(start_time__isnull=True),
            Q(end_time__gte=now) | Q(end_time__isnull=True),
        )

    def list(self, request, *args, **kwargs):
        """Graceful response if no banners or validation errors"""
        try:
            queryset = self.get_queryset()
            if not queryset.exists():
                return Response([])
            return Response(self.get_serializer(queryset, many=True).data)
        except ValidationError as e:
            return Response(e.detail, status=400)
        except Exception as e:
            # Proper logging should replace print in real production
            print(f"Error retrieving banners: {e}")
            return Response(
                {"error": "Unexpected error occurred while retrieving banners"},
                status=500,
            )
