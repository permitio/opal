package risk.authentication.resource.allow.policy_0257

# Auto-generated policy 257 (Rego v1 syntax)
# Package: risk.authentication.resource.allow

# Metadata
metadata := {
    "policy_id": "0257",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default policy_0257_allowed = false
policy_0257_allowed if {
    input.user.active
    input.resource.public
}
policy_0257_allowed if {
    input.user.role == "admin"
}
policy_0257_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
