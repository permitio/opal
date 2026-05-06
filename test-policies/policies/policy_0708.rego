package risk.monitoring.resource.verify.policy_0708

# Auto-generated policy 708 (Rego v1 syntax)
# Package: risk.monitoring.resource.verify

# Metadata
metadata := {
    "policy_id": "0708",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0708_allowed if {
    input.user.active
    input.resource.public
}
default policy_0708_allowed = false
policy_0708_allowed if {
    input.user.role == "admin"
}
