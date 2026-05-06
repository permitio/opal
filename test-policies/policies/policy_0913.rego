package governance.authentication.resource.verify.policy_0913

# Auto-generated policy 913 (Rego v1 syntax)
# Package: governance.authentication.resource.verify

# Metadata
metadata := {
    "policy_id": "0913",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0913_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0913_allowed if {
    input.user.active
    input.resource.public
}
