package security.enforcement.policy.verify.policy_0844

# Auto-generated policy 844 (Rego v1 syntax)
# Package: security.enforcement.policy.verify

# Metadata
metadata := {
    "policy_id": "0844",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0844_allowed if {
    input.user.role == "admin"
}
policy_0844_allowed if {
    input.user.active
    input.resource.public
}
policy_0844_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0844_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
