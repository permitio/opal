package access.monitoring.resource.verify.policy_0775

# Auto-generated policy 775 (Rego v1 syntax)
# Package: access.monitoring.resource.verify

# Metadata
metadata := {
    "policy_id": "0775",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0775_allowed if {
    input.user.role == "admin"
}
policy_0775_allowed if {
    data.policies.access.enabled
}
