package risk.enforcement.context.deny.policy_0317

# Auto-generated policy 317 (Rego v1 syntax)
# Package: risk.enforcement.context.deny

# Metadata
metadata := {
    "policy_id": "0317",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0317_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0317_allowed = false
