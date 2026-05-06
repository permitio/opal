package governance.monitoring.user.allow.policy_0439

# Auto-generated policy 439 (Rego v1 syntax)
# Package: governance.monitoring.user.allow

# Metadata
metadata := {
    "policy_id": "0439",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0439_allowed if {
    input.user.active
    input.resource.public
}
default policy_0439_allowed = false
policy_0439_allowed if {
    input.user.role == "admin"
}
