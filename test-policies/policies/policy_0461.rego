package risk.monitoring.resource.validate.policy_0461

# Auto-generated policy 461 (Rego v1 syntax)
# Package: risk.monitoring.resource.validate

# Metadata
metadata := {
    "policy_id": "0461",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0461_allowed if {
    data.policies.risk.enabled
}
policy_0461_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0461_allowed if {
    input.user.role == "admin"
}
default policy_0461_allowed = false
