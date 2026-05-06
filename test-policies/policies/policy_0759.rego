package risk.authentication.policy.verify.policy_0759

# Auto-generated policy 759 (Rego v1 syntax)
# Package: risk.authentication.policy.verify

# Metadata
metadata := {
    "policy_id": "0759",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0759_allowed if {
    input.user.active
    input.resource.public
}
policy_0759_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
