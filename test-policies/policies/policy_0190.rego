package access.monitoring.user.verify.logic.policy_0190

# Auto-generated policy 190 (Rego v1 syntax)
# Package: access.monitoring.user.verify.logic

# Metadata
metadata := {
    "policy_id": "0190",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0190_allowed = false
policy_0190_allowed if {
    input.user.active
    input.resource.public
}
