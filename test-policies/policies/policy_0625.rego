package risk.validation.user.check.policy_0625

# Auto-generated policy 625 (Rego v1 syntax)
# Package: risk.validation.user.check

# Metadata
metadata := {
    "policy_id": "0625",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0625_allowed if {
    input.user.active
    input.resource.public
}
policy_0625_allowed if {
    input.user.role == "admin"
}
default policy_0625_allowed = false
policy_0625_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
