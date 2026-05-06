package governance.validation.resource.allow.policy_0630

# Auto-generated policy 630 (Rego v1 syntax)
# Package: governance.validation.resource.allow

# Metadata
metadata := {
    "policy_id": "0630",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0630_allowed = false
policy_0630_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0630_allowed if {
    input.user.active
    input.resource.public
}
