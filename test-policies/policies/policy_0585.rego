package risk.validation.action.deny.utils.policy_0585

# Auto-generated policy 585 (Rego v1 syntax)
# Package: risk.validation.action.deny.utils

# Metadata
metadata := {
    "policy_id": "0585",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0585_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0585_allowed if {
    input.user.active
    input.resource.public
}
default policy_0585_allowed = false
