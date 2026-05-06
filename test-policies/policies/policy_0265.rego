package compliance.authorization.policy.allow.policy_0265

# Auto-generated policy 265 (Rego v1 syntax)
# Package: compliance.authorization.policy.allow

# Metadata
metadata := {
    "policy_id": "0265",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0265_allowed if {
    input.user.active
    input.resource.public
}
policy_0265_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
