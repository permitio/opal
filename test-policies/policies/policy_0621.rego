package access.authentication.context.verify.helpers.policy_0621

# Auto-generated policy 621 (Rego v1 syntax)
# Package: access.authentication.context.verify.helpers

# Metadata
metadata := {
    "policy_id": "0621",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0621_allowed if {
    input.user.role == "admin"
}
policy_0621_allowed if {
    data.policies.access.enabled
}
