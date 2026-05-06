package risk.authentication.resource.deny.policy_0692

# Auto-generated policy 692 (Rego v1 syntax)
# Package: risk.authentication.resource.deny

# Metadata
metadata := {
    "policy_id": "0692",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0692_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0692_allowed = false
policy_0692_allowed if {
    input.user.role == "admin"
}
