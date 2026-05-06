package risk.authorization.policy.verify.policy_0507

# Auto-generated policy 507 (Rego v1 syntax)
# Package: risk.authorization.policy.verify

# Metadata
metadata := {
    "policy_id": "0507",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0507_allowed if {
    input.user.active
    input.resource.public
}
policy_0507_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
