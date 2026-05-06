package audit.monitoring.user.check.policy_0521

# Auto-generated policy 521 (Rego v1 syntax)
# Package: audit.monitoring.user.check

# Metadata
metadata := {
    "policy_id": "0521",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0521_allowed if {
    data.policies.audit.enabled
}
policy_0521_allowed if {
    input.user.role == "admin"
}
policy_0521_allowed if {
    input.user.active
    input.resource.public
}
default policy_0521_allowed = false
