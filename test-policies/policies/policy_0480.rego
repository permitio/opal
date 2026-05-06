package risk.authorization.resource.allow.policy_0480

# Auto-generated policy 480 (Rego v1 syntax)
# Package: risk.authorization.resource.allow

# Metadata
metadata := {
    "policy_id": "0480",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0480_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0480_allowed if {
    input.user.role == "admin"
}
