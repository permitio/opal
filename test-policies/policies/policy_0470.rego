package risk.enforcement.resource.validate.policy_0470

# Auto-generated policy 470 (Rego v1 syntax)
# Package: risk.enforcement.resource.validate

# Metadata
metadata := {
    "policy_id": "0470",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0470_allowed if {
    input.user.active
    input.resource.public
}
default policy_0470_allowed = false
policy_0470_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
