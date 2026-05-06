package risk.monitoring.resource.deny.helpers.policy_0281

# Auto-generated policy 281 (Rego v1 syntax)
# Package: risk.monitoring.resource.deny.helpers

# Metadata
metadata := {
    "policy_id": "0281",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0281_allowed if {
    input.user.active
    input.resource.public
}
policy_0281_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0281_allowed = false
